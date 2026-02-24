from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import fitz  # PyMuPDF
import torch
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

EMBED_DIM = 128  # ColQwen2 pooled embedding size
COLLECTION = "papers"
LEGACY_COLLECTIONS = ("papers_text", "papers_visual")

_model = None
_processor = None
_client = None


def get_model():
    """Lazily load the ColQwen2 model and processor."""
    global _model, _processor
    if _model is None:
        from colpali_engine.models import ColQwen2, ColQwen2Processor

        _model = ColQwen2.from_pretrained(
            "vidore/colqwen2-v1.0",
            torch_dtype=torch.float32,
        )
        _model.eval()
        _processor = ColQwen2Processor.from_pretrained("vidore/colqwen2-v1.0")
    return _model, _processor


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(path="./qdrant_db")
    return _client


def _collection_exists(client: QdrantClient, name: str) -> bool:
    try:
        client.get_collection(name)
        return True
    except Exception:
        return False


def _safe_delete_collection(client: QdrantClient, name: str) -> None:
    try:
        client.delete_collection(name)
        print(f"Removed legacy collection '{name}'")
    except Exception:
        # Missing collection and unsupported delete API variants are both fine.
        pass


def create_collection(recreate: bool = False, drop_legacy: bool = True) -> None:
    """Ensure the unified page-level collection exists.

    `recreate=False` is non-destructive by default. Use `recreate=True` for a full
    rebuild. Legacy collections can optionally be removed after cutover.
    """
    client = get_client()

    if recreate:
        client.recreate_collection(
            COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        print(f"Recreated '{COLLECTION}' collection")
    elif not _collection_exists(client, COLLECTION):
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        print(f"Created '{COLLECTION}' collection")
    else:
        print(f"Using existing '{COLLECTION}' collection")

    if drop_legacy:
        for legacy_name in LEGACY_COLLECTIONS:
            if legacy_name != COLLECTION:
                _safe_delete_collection(client, legacy_name)


def _mean_pool_tensor(sample: torch.Tensor) -> list[float]:
    if sample.ndim == 1:
        pooled = sample
    else:
        pooled = sample.mean(dim=0)
    return pooled.detach().cpu().numpy().tolist()


def _pool_batch_outputs(outputs) -> list[list[float]]:
    """Pool ColQwen2 outputs into one vector per input image/query."""
    vectors: list[list[float]] = []

    try:
        num_items = len(outputs)
    except TypeError as exc:  # pragma: no cover - defensive
        raise TypeError("Unexpected embedding output type from ColQwen2") from exc

    for i in range(num_items):
        sample = outputs[i]
        if not isinstance(sample, torch.Tensor):
            raise TypeError("Unexpected ColQwen2 sample output type")
        vectors.append(_mean_pool_tensor(sample))
    return vectors


def embed_pages(images, batch_size: int = 8) -> list[list[float]]:
    """Embed page images using ColQwen2 in sub-batches to reduce memory spikes."""
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if not images:
        return []

    model, processor = get_model()
    all_vectors: list[list[float]] = []

    for start in range(0, len(images), batch_size):
        batch = images[start:start + batch_size]
        inputs = processor.process_images(batch)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            all_vectors.extend(_pool_batch_outputs(outputs))

    return all_vectors


def embed_query(query: str) -> list[float]:
    """Embed a text query using ColQwen2 query encoder path."""
    model, processor = get_model()
    inputs = processor.process_queries([query])
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
    vectors = _pool_batch_outputs(outputs)
    return vectors[0]


def _pdf_fingerprint(pdf_path: str) -> str:
    st = os.stat(pdf_path)
    payload = f"{os.path.abspath(pdf_path)}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _point_id(pdf_path: str, page_num: int, fingerprint: str) -> int:
    seed = f"{os.path.abspath(pdf_path)}|{page_num}|{fingerprint}"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def _render_page_image(page, dpi_scale: float):
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale), alpha=False)
    if pix.n == 1:
        mode = "L"
    elif pix.n >= 4:
        mode = "RGBA"
    else:
        mode = "RGB"

    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _flush_batch(
    *,
    client: QdrantClient,
    pdf_path: str,
    fingerprint: str,
    batch_images,
    batch_rows: list[dict],
    batch_size: int,
) -> int:
    if not batch_rows:
        return 0

    vectors = embed_pages(batch_images, batch_size=batch_size)
    indexed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    points: list[PointStruct] = []

    if len(batch_rows) != len(vectors):
        raise ValueError(
            f"batch_rows/vectors length mismatch: {len(batch_rows)} vs {len(vectors)}"
        )
    for row, vector in zip(batch_rows, vectors):
        points.append(
            PointStruct(
                id=_point_id(pdf_path, row["page"], fingerprint),
                vector=vector,
                payload={
                    "pdf": pdf_path,
                    "page": row["page"],
                    "text": row["text"],
                    "type": "page",
                    "char_count": row["char_count"],
                    "indexed_at": indexed_at,
                },
            )
        )

    if points:
        client.upsert(COLLECTION, points)

    return len(points)


def index_pdf(pdf_path: str, batch_size: int = 8, dpi_scale: float = 2.0) -> dict:
    """Render PDF pages to images, embed them, and upsert to the unified collection."""
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if dpi_scale <= 0:
        raise ValueError("dpi_scale must be > 0")

    client = get_client()
    fingerprint = _pdf_fingerprint(pdf_path)

    doc = fitz.open(pdf_path)
    pages_seen = len(doc)
    pages_indexed = 0

    batch_images = []
    batch_rows: list[dict] = []

    try:
        for page_idx in range(pages_seen):
            page = doc[page_idx]
            page_num = page_idx + 1
            text = page.get_text() or ""
            image = _render_page_image(page, dpi_scale)

            batch_images.append(image)
            batch_rows.append(
                {
                    "page": page_num,
                    "text": text,
                    "char_count": len(text),
                }
            )

            if len(batch_rows) >= batch_size:
                pages_indexed += _flush_batch(
                    client=client,
                    pdf_path=pdf_path,
                    fingerprint=fingerprint,
                    batch_images=batch_images,
                    batch_rows=batch_rows,
                    batch_size=batch_size,
                )
                batch_images.clear()
                batch_rows.clear()

        if batch_rows:
            pages_indexed += _flush_batch(
                client=client,
                pdf_path=pdf_path,
                fingerprint=fingerprint,
                batch_images=batch_images,
                batch_rows=batch_rows,
                batch_size=batch_size,
            )
    finally:
        doc.close()

    result = {
        "pdf": pdf_path,
        "pages_seen": pages_seen,
        "pages_indexed": pages_indexed,
        "collection": COLLECTION,
    }
    print(f"  Indexed {pages_indexed}/{pages_seen} pages into '{COLLECTION}'")
    return result


def search(query: str, top_k: int = 5) -> list:
    """Query the unified collection with a text query embedded by ColQwen2."""
    client = get_client()
    q_emb = embed_query(query)
    results = client.query_points(
        collection_name=COLLECTION,
        query=q_emb,
        limit=top_k,
    )
    return results.points


def search_all(query: str, top_k: int = 5) -> dict:
    """Compatibility shim preserving the old API shape during migration."""
    page_results = search(query, top_k)
    return {
        "pages": page_results,
        "text": page_results,
        "figures": [],
    }
