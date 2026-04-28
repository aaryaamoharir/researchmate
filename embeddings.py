from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import logging

import fitz  # PyMuPDF
import torch
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from dotenv import load_dotenv
from llm_client import get_chat_model, get_groq_client

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
    """Ensure the page-level collection exists.

    `recreate=False` is non-destructive by default. Use `recreate=True` for a full rebuild.
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


def _summarize_page(text: str, pdf_name: str, page_num: int, image=None) -> str:
    """Summarize a page using Gemini vision (image) with text fallback to Groq."""
    if image is not None:
        try:
            result = _summarize_page_gemini(image, pdf_name, page_num)
            print(f"    [Gemini] Summarized page {page_num}")
            return result
        except Exception as exc:
            print(f"    [Gemini FAILED] page {page_num}: {exc}")
            logger.warning(
                "Gemini summary failed (%s p%d), falling back to text: %s",
                pdf_name, page_num, exc,
            )
    # Fallback: text-only summary via Groq
    if not text.strip():
        return ""
    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            model=get_chat_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a research assistant. Summarize ONLY the content on "
                        "this specific page in 2-4 sentences. Focus on what makes this "
                        "page unique — what specific topic, data, method, figure, or "
                        "argument appears HERE and not on other pages. "
                        "Do NOT give a general overview of the whole paper. "
                        "Do NOT reproduce any raw text, equations, or math notation. "
                        "If the page is a references list or mostly boilerplate, say so briefly."
                    ),
                },
                {
                    "role": "user",
                    "content": f"[{pdf_name} - Page {page_num}]\n\n{text[:8000]}",
                },
            ],
            temperature=0.3,
            max_tokens=256,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("Page summary failed (%s p%d): %s", pdf_name, page_num, exc)
        return ""


def _summarize_page_gemini(image, pdf_name: str, page_num: int) -> str:
    """Summarize a page image using Gemini vision (new google.genai SDK)."""
    import io

    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY")

    client = genai.Client(api_key=api_key)

    # Convert PIL image to bytes
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    prompt = (
        f"This is page {page_num} from the research paper '{pdf_name}'. "
        "Summarize ONLY the content on this specific page in 2-4 sentences. "
        "Describe any figures, diagrams, tables, or charts you see — what they "
        "show, their axes, trends, and key takeaways. "
        "Focus on what makes this page unique. "
        "Do NOT give a general overview of the whole paper. "
        "Do NOT reproduce raw equations or math notation."
    )

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        ],
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=1024,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return response.text or ""


def _summarize_paper(page_summaries: list[str], pdf_name: str) -> str:
    """Generate a summary-of-summaries for the entire paper."""
    combined = "\n\n".join(
        f"Page {i+1}: {s}" for i, s in enumerate(page_summaries) if s
    )
    if not combined.strip():
        return ""
    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            model=get_chat_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a research assistant. Given per-page summaries of a "
                        "research paper, produce a comprehensive summary of the entire "
                        "paper. Include: 1) Main objective/problem, 2) Key methodology, "
                        "3) Main findings/results, 4) Conclusions. Keep it concise "
                        "(3-5 paragraphs)."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Paper: {pdf_name}\n\nPage summaries:\n{combined}",
                },
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("Paper summary failed (%s): %s", pdf_name, exc)
        return ""


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
                    "summary": row.get("summary", ""),
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
    pdf_name = os.path.basename(pdf_path)

    # Optional Supabase sync — skips silently if not configured or not installed
    _supabase_sync = False
    _sb_insert_pdf = None
    _sb_insert_page = None
    _sb_insert_summary = None
    try:
        if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"):
            from supabase_client import insert_pdf, insert_pdf_page, insert_paper_summary

            _sb_insert_pdf = insert_pdf
            _sb_insert_page = insert_pdf_page
            _sb_insert_summary = insert_paper_summary
            _supabase_sync = True
    except ImportError:
        logger.info("supabase package not installed — skipping Supabase sync")

    doc = fitz.open(pdf_path)
    pages_seen = len(doc)
    pages_indexed = 0

    batch_images = []
    batch_rows: list[dict] = []
    all_page_summaries: list[str] = []
    paper_summary = ""

    # Insert PDF record into Supabase
    supabase_pdf_id = None
    if _supabase_sync:
        try:
            supabase_pdf_id = _sb_insert_pdf(pdf_name)
            print(f"  Created Supabase PDF record (id={supabase_pdf_id})")
        except Exception as exc:
            logger.warning("Supabase PDF insert failed: %s", exc)

    try:
        for page_idx in range(pages_seen):
            page = doc[page_idx]
            page_num = page_idx + 1
            text = page.get_text() or ""
            image = _render_page_image(page, dpi_scale)

            # Summarize this page
            print(f"  Summarizing page {page_num}/{pages_seen}...")
            page_summary = _summarize_page(text, pdf_name, page_num, image=image)
            all_page_summaries.append(page_summary)

            # Sync page summary to Supabase
            if supabase_pdf_id is not None:
                try:
                    _sb_insert_page(supabase_pdf_id, page_num, page_summary)
                except Exception as exc:
                    logger.warning("Supabase page insert failed (p%d): %s", page_num, exc)

            batch_images.append(image)
            batch_rows.append(
                {
                    "page": page_num,
                    "text": text,
                    "summary": page_summary,
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

        # Generate and store paper-level summary-of-summaries
        print(f"  Generating paper summary...")
        paper_summary = _summarize_paper(all_page_summaries, pdf_name)
        if paper_summary:
            summary_point_id = _point_id(pdf_path, 0, fingerprint)
            indexed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            # Use a zero vector — this point is for lookup, not similarity search
            zero_vector = [0.0] * EMBED_DIM
            client.upsert(
                COLLECTION,
                [
                    PointStruct(
                        id=summary_point_id,
                        vector=zero_vector,
                        payload={
                            "pdf": pdf_path,
                            "page": 0,
                            "text": paper_summary,
                            "summary": paper_summary,
                            "type": "paper_summary",
                            "page_summaries": all_page_summaries,
                            "char_count": len(paper_summary),
                            "indexed_at": indexed_at,
                        },
                    )
                ],
            )
            print(f"  Stored paper summary")

            # Sync paper summary to Supabase
            if supabase_pdf_id is not None:
                try:
                    _sb_insert_summary(supabase_pdf_id, paper_summary)
                    print(f"  Stored paper summary in Supabase")
                except Exception as exc:
                    logger.warning("Supabase summary insert failed: %s", exc)
    finally:
        doc.close()

    result = {
        "pdf": pdf_path,
        "pages_seen": pages_seen,
        "pages_indexed": pages_indexed,
        "paper_summary": paper_summary,
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
