"""Supabase client helpers for storing PDF metadata and summaries."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
except ImportError:
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


def _delete_pdf(file_name: str) -> None:
    """Delete existing rows for this PDF from all tables."""
    client = get_supabase_client()
    existing = client.table("pdfs").select("id").eq("file_name", file_name).execute()
    for row in existing.data:
        client.table("pdf_pages").delete().eq("pdf_id", row["id"]).execute()
        client.table("summaries").delete().eq("pdf_id", row["id"]).execute()
    client.table("pdfs").delete().eq("file_name", file_name).execute()


def upsert_pdf(file_name: str, userid: str | None = None) -> int:
    """Delete any existing rows for this PDF, then insert fresh. Returns the new id."""
    client = get_supabase_client()
    _delete_pdf(file_name)
    row = {"file_name": file_name}
    if userid:
        row["userid"] = userid
    result = client.table("pdfs").insert(row).execute()
    return result.data[0]["id"]


def insert_pdf_pages(pdf_id: int, page_summaries: list[str]) -> None:
    """Batch-insert all page summaries for a PDF in one request."""
    if not page_summaries:
        return
    client = get_supabase_client()
    rows = [
        {"pdf_id": pdf_id, "page_number": i + 1, "summary": summary}
        for i, summary in enumerate(page_summaries)
    ]
    client.table("pdf_pages").insert(rows).execute()


def insert_paper_summary(pdf_id: int, summary: str) -> None:
    """Insert the paper-level summary into the summaries table."""
    client = get_supabase_client()
    client.table("summaries").insert(
        {"pdf_id": pdf_id, "summary": summary}
    ).execute()
