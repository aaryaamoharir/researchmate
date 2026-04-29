

from __future__ import annotations

import io
import os
import time
import logging

from dotenv import load_dotenv
from PIL import Image
from supabase import create_client

load_dotenv()

logger = logging.getLogger(__name__)

_PROMPT = (
    "Summarize ONLY the content on this specific page in 2-4 sentences. "
    "Focus on what makes this page unique — what specific topic, data, method, "
    "figure, or argument appears HERE and not on other pages. "
    "Do NOT give a general overview of the whole paper. "
    "Do NOT reproduce any raw text, equations, or math notation. "
    "If the page is a references list or mostly boilerplate, say so briefly. "
    "Describe any figures, diagrams, tables, or charts you see — what they "
    "show, their axes, trends, and key takeaways."
)

_gemini_client = None
_supabase_admin = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Missing GEMINI_API_KEY")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _get_supabase_admin():
    global _supabase_admin
    if _supabase_admin is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Missing SUPABASE_URL and SUPABASE_SERVICE_KEY/SUPABASE_KEY")
        _supabase_admin = create_client(url, key)
    return _supabase_admin


def _download_image(supabase_path: str) -> Image.Image:
    raw_bytes = _get_supabase_admin().storage.from_("pdf-pages").download(supabase_path)
    return Image.open(io.BytesIO(raw_bytes)).convert("RGB")


def _call_gemini(image: Image.Image, pdf_name: str, page_num: int, max_retries: int = 3) -> str:
    from google.genai import types

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    image_bytes = buf.getvalue()
    buf.close()

    prompt = f"This is page {page_num} from the research paper '{pdf_name}'. " + _PROMPT
    gemini = _get_gemini_client()

    for attempt in range(max_retries):
        try:
            response = gemini.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[
                    prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                ],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=1024,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            return response.text or ""
        except Exception as exc:
            if attempt < max_retries - 1 and ("503" in str(exc) or "UNAVAILABLE" in str(exc)):
                wait = 2 ** attempt
                logger.warning("Gemini 503 on page %d, retrying in %ds...", page_num, wait)
                time.sleep(wait)
            else:
                raise


def generate_summary(supabase_path: str) -> str:
    
    parts = supabase_path.split("/")
    page_num = int(parts[-1].replace(".png", ""))
    pdf_name = parts[1] if len(parts) > 1 else "unknown"

    try:
        image = _download_image(supabase_path)
        return _call_gemini(image, pdf_name, page_num)
    except Exception as exc:
        logger.error("generate_summary failed for %s: %s", supabase_path, exc)
        raise
