import asyncio
from models import PDF_Pages
from summarize import generate_summary        
from db import SessionLocal


def call_agent(page):
    return generate_summary(page.supabase_path) #filler, cahnge later

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

                except Exception as e:
                    print("Error:", e)
                    page.summary = "failed"
                    db.commit()

                

        finally:
            db.close()

        await asyncio.sleep(5)  # Sleep for a while before checking for new pages