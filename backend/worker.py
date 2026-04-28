import asyncio
from main import SessionLocal
from main import PDF_Pages
from agent.tools.summarize import generate_summary #whatever the agent path is


def call_agent(page):
    return generate_summary(page.supabase_path) #filler, cahnge later


async def summary_worker():
    while True:
        db = SessionLocal()

        try:
            pages = (
                db.query(PDF_Pages)
                .filter(PDF_Pages.summary == "empty")
                .limit(5)
                .all()
            )

            for page in pages:
                page.summary = "processing"
                db.commit()

                try:
                    call_agent(page) #calls agent and stores in db

                except Exception as e:
                    print("Error:", e)
                    page.summary = "failed" #create a failed state, or we can just switch back to empty(saves time)
                    db.commit()

                

        finally:
            db.close()

        await asyncio.sleep(2)