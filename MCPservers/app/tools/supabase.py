from __future__ import annotations
import os
from pydoc import text
import httpx
from dotenv import load_dotenv
import re
import json

load_dotenv()

SUPABASE_MCP_URL = (
    "https://mcp.supabase.com/mcp"
    "?project_ref=hbutreqslisuwsjifmas"
    "&features=storage%2Cdatabase%2Cdebugging%2Cdevelopment"
)

HEADERS = {
    "Authorization": f"Bearer {os.getenv('SUPABASE_PAT')}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

def get_session_id() -> str:
    """Initialize a session with Supabase MCP and return the session ID."""
    response = httpx.post(
        SUPABASE_MCP_URL,
        headers=HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "research-papers", "version": "1.0"},
                "capabilities": {}
            }
        },
        timeout=10.0
    )
    session_id = response.headers.get("mcp-session-id")
    return session_id

def supabase_sql(sql: str) -> list[dict]:
    """Call Supabase MCP execute_sql and return rows."""
    session_id = get_session_id()
    
    response = httpx.post(
        SUPABASE_MCP_URL,
        headers={**HEADERS, "Mcp-Session-Id": session_id},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "execute_sql",
                "arguments": {"query": sql}
            }
        },
        timeout=10.0
    )
    response.raise_for_status()
    
    text = response.json()["result"]["content"][0]["text"]
    text = json.loads(text)  # parse it again — it's a double-encoded string

    if isinstance(text, dict):
        text = text.get("result", "")

    # Now extract between the tags
    start = text.index("[")
    end = text.rindex("]") + 1
    return json.loads(text[start:end])

