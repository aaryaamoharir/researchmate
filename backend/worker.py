import asyncio
import logging
import os

from PIL import Image
from models import PDF_Pages, PDF
from summarize import generate_summary
from db import SessionLocal

logger = logging.getLogger(__name__)


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


async def summary_worker():
    while True:
        db = SessionLocal()

        try:
            pages = (
                db.query(PDF_Pages)
                .filter(PDF_Pages.summary == "empty")
                .filter(PDF_Pages.supabase_path != None)
                .limit(5)
                .all()
            )

            for page in pages:
                page.summary = "processing"
                db.commit()

                try:
                    page.summary = call_agent(page)
                    db.commit()

                    # Embed the page into Qdrant after successful summarization
                    try:
                        embed_page(page, db)
                    except Exception as e:
                        logger.warning("Embedding failed for page %d: %s", page.id, e)

                except Exception as e:
                    logger.error("Summarization error: %s", e)
                    page.summary = "failed"
                    db.commit()

        finally:
            db.close()

        await asyncio.sleep(5)
