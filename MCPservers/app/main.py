from __future__ import annotations
from mcp.server.fastmcp import FastMCP
from MCPservers.app.tools.supabase import supabase_sql
from MCPservers.app.tools.googlescholar import search_research

mcp = FastMCP("research-papers")
SUPABASE_PROJECT_URL = "https://hbutreqslisuwsjifmas.supabase.co"

@mcp.tool()
def get_paper(pdf_id: int) -> dict:
    """Get user_id, file_name, storage_path, and created_at for a paper by id."""
    return supabase_sql(
        f"SELECT user_id, file_name, storage_path, created_at FROM pdfs WHERE id = {pdf_id} LIMIT 1"
    )

@mcp.tool()
def create_paper(user_id: str, file_name: str, storage_path: str) -> dict:
    """Insert a new paper record into the pdfs table."""
    return supabase_sql(
        f"""
        INSERT INTO pdfs (user_id, file_name, storage_path)
        VALUES ('{user_id}', '{file_name}', '{storage_path}')
        RETURNING id, user_id, file_name, storage_path, created_at
        """
    )

@mcp.tool()
def get_summary(pdf_id: int) -> dict:
    """Get the summary for a paper by pdf_id."""
    return supabase_sql(
        f"SELECT id, pdf_id, summary, created_at FROM summaries WHERE pdf_id = {pdf_id} LIMIT 1"
    )


@mcp.tool()
def create_summary(pdf_id: int, summary: str) -> dict:
    """Insert a new summary for a paper."""
    return supabase_sql(
        f"""
        INSERT INTO summaries (pdf_id, summary)
        VALUES ({pdf_id}, '{summary}')
        RETURNING id, pdf_id, summary, created_at
        """
    )

@mcp.tool()
def get_pdf_page_urls(pdf_id: int) -> list[dict]:
    """Get all page image URLs for a PDF from Supabase storage."""
    rows = supabase_sql(
        f"SELECT id, pdf_id, image_path, supabase_path, created_at FROM pdf_pages WHERE pdf_id = {pdf_id} ORDER BY id"
    )
    for row in rows:
        path = row.get("supabase_path") or row.get("image_path")
        row["url"] = f"{SUPABASE_PROJECT_URL}/storage/v1/object/public/pdf-pages/{path}"
    return rows

@mcp.tool()
def get_pdf_page_url(pdf_id: int, page_number: int) -> str:
    """Get a single page image URL by pdf_id and page number."""
    rows = supabase_sql(
        f"""
        SELECT image_path, supabase_path
        FROM pdf_pages 
        WHERE pdf_id = {pdf_id} 
        ORDER BY id
        LIMIT 1 OFFSET {page_number - 1}
        """
    )
    if not rows:
        return ""
    row = rows[0]
    path = row.get("supabase_path") or row.get("image_path")
    return f"{SUPABASE_PROJECT_URL}/storage/v1/object/public/pdf-pages/{path}"

@mcp.tool()
def search_scholar(query: str, total_results: int = 10, date_restrict: str = "y1") -> list[dict]:
    """
    Search research-like results using Google Custom Search.
    date_restrict examples: d30, m6, y1, y5
    """
    return search_research(query, total_results=total_results, date_restrict=date_restrict, prefer_pdfs=True)

if __name__ == "__main__":
    mcp.run()

