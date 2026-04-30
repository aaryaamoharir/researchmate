import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from models import PDF_Pages, PDF
from summarize import generate_summary
from db import SessionLocal

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=5)


def call_agent(page):
    return generate_summary(page.supabase_path)


def embed_page(page, db):
    """Embed the page image and upsert to Qdrant after summarization."""
    from embeddings import embed_and_upsert_page

    # Build local image path from the page's image_path
    local_path = f"storage/{page.image_path}"
    if not os.path.exists(local_path):
        logger.warning("Image not found at %s — skipping embedding", local_path)
        return

    image = Image.open(local_path).convert("RGB")

    # Get the PDF name for metadata
    pdf = db.query(PDF).filter(PDF.id == page.pdf_id).first()
    pdf_name = pdf.file_name if pdf else ""

    embed_and_upsert_page(
        pdf_id=page.pdf_id,
        page_num=page.page_number,
        image=image,
        summary=page.summary,
        pdf_name=pdf_name,
    )


def _summarize_page(page_id: int) -> tuple[int, str]:
    """Summarize a single page in a thread. Returns (page_id, summary)."""
    db = SessionLocal()
    try:
        page = db.query(PDF_Pages).filter(PDF_Pages.id == page_id).first()
        if not page:
            return page_id, "failed"
        summary = call_agent(page)
        return page_id, summary
    except Exception as e:
        logger.error("Summarization error for page %d: %s", page_id, e)
        return page_id, "failed"
    finally:
        db.close()


async def summary_worker():
    while True:
        db = SessionLocal()

        try:
            pages = (
                db.query(PDF_Pages)
                .filter(PDF_Pages.summary == "empty")
                .filter(PDF_Pages.supabase_path != None)
                .limit(10)
                .all()
            )

            if not pages:
                await asyncio.sleep(2)
                continue

            # Mark all as processing
            page_ids = []
            for page in pages:
                page.summary = "processing"
                page_ids.append(page.id)
            db.commit()

            # Summarize concurrently via thread pool
            loop = asyncio.get_event_loop()
            tasks = [loop.run_in_executor(_executor, _summarize_page, pid) for pid in page_ids]
            results = await asyncio.gather(*tasks)

            # Update summaries and embed
            for page_id, summary in results:
                page = db.query(PDF_Pages).filter(PDF_Pages.id == page_id).first()
                if not page:
                    continue
                page.summary = summary
                db.commit()

                if summary not in ("failed", "processing", "empty"):
                    try:
                        embed_page(page, db)
                    except Exception as e:
                        logger.warning("Embedding failed for page %d: %s", page.id, e)

        finally:
            db.close()

        await asyncio.sleep(1)
