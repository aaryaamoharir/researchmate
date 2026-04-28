
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

_client = None


def get_supabase_client():
    """Return a singleton Supabase client."""
    global _client
    if _client is None:
        from supabase import create_client

        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError(
                "Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_KEY."
            )
        _client = create_client(url, key)
    return _client


def delete_pdf(file_name: str) -> None:
    client = get_supabase_client()
    # Find existing pdf rows with this filename
    existing = client.table("pdfs").select("id").eq("file_name", file_name).execute()
    for row in existing.data:
        # Delete child pages and summary first
        client.table("pdf_pages").delete().eq("pdf_id", row["id"]).execute()
        client.table("summaries").delete().eq("pdf_id", row["id"]).execute()
    # Delete the pdf row(s)
    client.table("pdfs").delete().eq("file_name", file_name).execute()


def insert_pdf(file_name: str, userid: str | None = None) -> int:
    client = get_supabase_client()
    delete_pdf(file_name)
    row = {"file_name": file_name}
    if userid:
        row["userid"] = userid
    result = client.table("pdfs").insert(row).execute()
    return result.data[0]["id"]


def insert_pdf_page(pdf_id: int, page_number: int, summary: str) -> None:
    """Insert a row into the pdf_pages table."""
    client = get_supabase_client()
    client.table("pdf_pages").insert(
        {
            "pdf_id": pdf_id,
            "page_number": page_number,
            "summary": summary,
        }
    ).execute()


def insert_paper_summary(pdf_id: int, summary: str) -> None:
    """Insert the paper-level summary into the summaries table."""
    client = get_supabase_client()
    client.table("summaries").insert(
        {
            "pdf_id": pdf_id,
            "summary": summary,
        }
    ).execute()
