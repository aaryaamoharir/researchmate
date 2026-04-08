from __future__ import annotations

import os
import math
import time
import re
import httpx
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://www.googleapis.com/customsearch/v1"

# DO NOT hardcode keys
API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("GOOGLE_CSE_CX")

# Very light “research bias” filters (MVP)
ACADEMIC_DOMAIN_HINTS = (
    "openreview.net",
    "semanticscholar.org",
    "core.ac.uk",
    "doaj.org",
    "dblp.org",
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "link.springer.com",
    "sciencedirect.com",
    "nature.com",
    "science.org",
    "doi.org",
)

def _build_query(query: str, *, prefer_pdfs: bool = True) -> str:
    q = query.strip()

    paperish = '(paper OR "research paper" OR journal OR conference OR preprint OR DOI)'
    site_clause = " OR ".join([f"site:{d}" for d in ACADEMIC_DOMAIN_HINTS])

    q = f"{q} {paperish} ({site_clause})"

    if prefer_pdfs:
        q = f"{q} filetype:pdf"

    return q

def _build_payload(query: str, *, start: int = 1, num: int = 10, date_restrict: str | None = None, **params):
    if not API_KEY or not SEARCH_ENGINE_ID:
        raise RuntimeError("Missing GOOGLE_CSE_API_KEY or GOOGLE_CSE_CX in env.")

    payload = {
        "key": API_KEY,
        "cx": SEARCH_ENGINE_ID,
        "q": query,
        "start": start,              # 1-based
        "num": min(10, max(1, num)), # cap
    }
    if date_restrict:
        payload["dateRestrict"] = date_restrict  # e.g., "m1", "y2", "d30"
    payload.update(params)
    return payload


def _make_request(payload, *, timeout=20, max_retries=3, backoff=1.7):
    for attempt in range(max_retries):
        try:
            r = httpx.get(API_URL, params=payload, timeout=timeout)
            if r.status_code == 429:
                time.sleep(backoff ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(data["error"].get("message", "Unknown API error"))
            return data
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff ** attempt)
    return {}


def _looks_academic(url: str) -> bool:
    u = (url or "").lower()
    if u.endswith(".pdf"):
        return True
    return any(dom in u for dom in ACADEMIC_DOMAIN_HINTS)


def search_research(query: str, *, total_results: int = 20, date_restrict: str | None = None, prefer_pdfs: bool = True) -> list[dict]:
    """
    Returns a clean list of results:
      [{title, url, snippet, source}]
    """
    q = _build_query(query, prefer_pdfs=prefer_pdfs)

    total = max(1, min(100, int(total_results)))  # CSE: first 100 results window
    pages = math.ceil(total / 10)
    items: list[dict] = []

    for i in range(pages):
        start = 1 + i * 10
        remaining = total - len(items)
        num = min(10, remaining)

        payload = _build_payload(q, start=start, num=num, date_restrict=date_restrict)
        data = _make_request(payload)
        batch = data.get("items", []) or []
        if not batch:
            break

        for it in batch:
            url = it.get("link", "")
            if not url:
                continue
            # MVP filter: keep paper-ish URLs
            if _looks_academic(url):
                items.append(
                    {
                        "title": it.get("title", ""),
                        "url": url,
                        "snippet": it.get("snippet", ""),
                        "source": it.get("displayLink", ""),
                    }
                )

        if len(items) >= total:
            break

        time.sleep(0.2)

    return items[:total]