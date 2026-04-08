from __future__ import annotations

import os
import re
from typing import List, Dict, Optional

import requests
import feedparser


ARXIV_API = "https://export.arxiv.org/api/query"


def _normalize_query(q: str) -> str:
    # arXiv API expects search_query like: all:computer vision
    q = q.strip()
    if not q:
        raise ValueError("query is empty")
    # If user didn’t specify a field, default to all:
    if ":" not in q:
        q = "all:" + q
    return q


def search_arxiv(query: str, max_results: int = 5, start: int = 0, sort_by: str = "relevance") -> List[Dict]:
    """
    Returns a list of dicts:
      [{arxiv_id, title, authors, published, updated, abstract, abs_url, pdf_url, categories}]
    """
    max_results = max(1, min(int(max_results), 50))
    start = max(0, int(start))

    q = _normalize_query(query)

    params = {
        "search_query": q,
        "start": start,
        "max_results": max_results,
        "sortBy": sort_by,     # relevance | lastUpdatedDate | submittedDate
        "sortOrder": "descending",
    }

    r = requests.get(ARXIV_API, params=params, timeout=20)
    r.raise_for_status()

    feed = feedparser.parse(r.text)
    out: List[Dict] = []

    for entry in feed.entries:
        abs_url = entry.get("link", "") or entry.get("id", "")
        # entry.id is like http://arxiv.org/abs/XXXX.YYYYvN
        raw_id = entry.get("id", "")
        arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id

        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        authors = [a.name for a in (entry.get("authors") or []) if getattr(a, "name", None)]
        categories = [t["term"] for t in (entry.get("tags") or []) if isinstance(t, dict) and "term" in t]

        out.append(
            {
                "arxiv_id": arxiv_id,
                "title": (entry.get("title") or "").strip().replace("\n", " "),
                "authors": authors,
                "published": entry.get("published", ""),
                "updated": entry.get("updated", ""),
                "abstract": (entry.get("summary") or "").strip().replace("\n", " "),
                "abs_url": abs_url,
                "pdf_url": pdf_url,
                "categories": categories,
            }
        )

    return out


def download_arxiv_pdf(pdf_url: str, output_dir: str = "arxiv_pdfs") -> str:
    """
    Downloads the PDF and returns the local file path.
    Keep separate from search so your tool isn't slow by default.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Extract id for filename
    m = re.search(r"/pdf/([^/]+)\.pdf", pdf_url)
    arxiv_id = m.group(1) if m else "paper"
    filename = os.path.join(output_dir, f"{arxiv_id.replace('/', '_')}.pdf")

    r = requests.get(pdf_url, timeout=30)
    r.raise_for_status()
    with open(filename, "wb") as f:
        f.write(r.content)
    return filename