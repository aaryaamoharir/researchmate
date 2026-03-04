import os
import math
import time
import requests

API_URL = "https://www.googleapis.com/customsearch/v1"
API_KEY = 'AIzaSyC6qmA7UENTD5QOcbqcjowrS7gKRHEO_H0'
SEARCH_ENGINE_ID = 'a6347fb72e8294741'

def build_payload(query, *, start=1, num=10, date_restrict=None, **params):
    if not API_KEY or not SEARCH_ENGINE_ID:
        raise RuntimeError("Missing GOOGLE_CSE_API_KEY or GOOGLE_CSE_CX env vars.")
    payload = {
        "key": API_KEY,
        "cx": SEARCH_ENGINE_ID,
        "q": query,
        "start": start,                # 1-based
        "num": min(10, max(1, num)),   # Google caps to 10
    }
    if date_restrict:                  # e.g., "m1", "y2", "d30"
        payload["dateRestrict"] = date_restrict
    payload.update(params)
    return payload

def make_request(payload, *, timeout=20, max_retries=3, backoff=1.5):
    for attempt in range(max_retries):
        try:
            r = requests.get(API_URL, params=payload, timeout=timeout)
            if r.status_code == 429:
                # simple backoff on rate limit
                time.sleep(backoff ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                # bubble up helpful API error details
                raise RuntimeError(data["error"].get("message", "Unknown API error"))
            return data
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff ** attempt)
    return {}

def search_cse(query, *, total_results=35, date_restrict="m1", extra_params=None):
    # Respect Google’s accessible window: first 100 results max
    total = max(1, min(100, total_results))
    pages = math.ceil(total / 10)
    all_items = []

    for i in range(pages):
        # starts at 1, 11, 21, ...
        start = 1 + i * 10
        remaining = total - len(all_items)
        num = min(10, remaining)
        payload = build_payload(
            query,
            start=start,
            num=num,
            date_restrict=date_restrict,
            **(extra_params or {})
        )
        data = make_request(payload)
        items = data.get("items", [])
        if not items:
            # no more results / quota / exhausted
            break
        all_items.extend(items)
        if len(all_items) >= total:
            break
        time.sleep(0.2)  # be polite

    return all_items

if __name__ == "__main__":
    results = search_cse("Machine Learning", total_results=10, date_restrict="m1")
    print(f"Fetched {len(results)} results")
    # Example: print titles
    for i, it in enumerate(results, 1):
        print(f"{i:02d}. {it.get('title')} — {it.get('link')}")
