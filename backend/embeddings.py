"""ColQwen2 embedding + Qdrant vector operations for the RAG pipeline."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone

import torch
from dotenv import load_dotenv
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PayloadSchemaType, PointStruct, VectorParams

load_dotenv()

logger = logging.getLogger(__name__)

EMBED_DIM = 128  # ColQwen2 pooled embedding size
COLLECTION = "papers"

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
    """Return a singleton Qdrant client (remote or local fallback)."""
    global _client
    if _client is None:
        url = os.environ.get("QDRANT_URL")
        api_key = os.environ.get("QDRANT_API_KEY")
        if url and api_key:
            _client = QdrantClient(url=url, api_key=api_key)
        else:
            _client = QdrantClient(path="./qdrant_db")
    return _client


def _collection_exists(client: QdrantClient, name: str) -> bool:
    try:
        client.get_collection(name)
        return True
    except Exception:
        return False


def create_collection(recreate: bool = False) -> None:
    """Ensure the Qdrant collection exists."""
    client = get_client()

    if recreate:
        client.recreate_collection(
            COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        logger.info("Recreated '%s' collection", COLLECTION)
    elif not _collection_exists(client, COLLECTION):
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        logger.info("Created '%s' collection", COLLECTION)
    else:
        logger.info("Using existing '%s' collection", COLLECTION)

    # Ensure payload index exists for pdf_id filtering
    try:
        client.create_payload_index(
            COLLECTION, "pdf_id", field_schema=PayloadSchemaType.INTEGER,
        )
    except Exception:
        pass  # Index already exists


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
    except TypeError as exc:
        raise TypeError("Unexpected embedding output type from ColQwen2") from exc

    for i in range(num_items):
        sample = outputs[i]
        if not isinstance(sample, torch.Tensor):
            raise TypeError("Unexpected ColQwen2 sample output type")
        vectors.append(_mean_pool_tensor(sample))
    return vectors


def embed_pages(images, batch_size: int = 8) -> list[list[float]]:
    """Embed page images using ColQwen2 in sub-batches."""
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


def _point_id(pdf_id: int, page_num: int) -> int:
    """Generate a deterministic point ID from pdf_id and page number."""
    seed = f"{pdf_id}|{page_num}"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def embed_and_upsert_page(
    pdf_id: int,
    page_num: int,
    image: Image.Image,
    summary: str,
    pdf_name: str = "",
) -> None:
    """Embed a single page image and upsert it to Qdrant.

    Called by the worker after Gemini summarization is complete.
    """
    client = get_client()
    create_collection()

    vectors = embed_pages([image], batch_size=1)
    if not vectors:
        logger.warning("No vector produced for pdf_id=%d page %d", pdf_id, page_num)
        return

    indexed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    point = PointStruct(
        id=_point_id(pdf_id, page_num),
        vector=vectors[0],
        payload={
            "pdf_id": pdf_id,
            "pdf": pdf_name,
            "page": page_num,
            "summary": summary,
            "type": "page",
            "indexed_at": indexed_at,
        },
    )
    client.upsert(COLLECTION, [point])
    logger.info("Upserted page %d of pdf_id=%d to Qdrant", page_num, pdf_id)


def search(query: str, top_k: int = 10, pdf_id: int | None = None) -> list:
    """Query the collection with a text query embedded by ColQwen2.

    If pdf_id is provided, only search pages from that specific paper.
    """
    client = get_client()
    q_emb = embed_query(query)

    search_filter = None
    if pdf_id is not None:
        search_filter = Filter(
            must=[FieldCondition(key="pdf_id", match=MatchValue(value=pdf_id))]
        )

    results = client.query_points(
        collection_name=COLLECTION,
        query=q_emb,
        query_filter=search_filter,
        limit=top_k,
    )
    return results.points
