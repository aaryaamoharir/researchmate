"""Shared LLM client helpers for Groq.

Centralizes API key lookup, base URL, and model defaults so
callers (agent, embeddings, summarizer) stay consistent.
"""

from __future__ import annotations

import os

from openai import OpenAI

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in some environments
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

_client: OpenAI | None = None


def get_groq_client() -> OpenAI:
    """Return a singleton OpenAI client configured for Groq."""
    global _client

    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("Missing API key. Set GROQ_API_KEY.")
        base_url = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client



def get_chat_model() -> str:
    """Return the configured chat model (defaults to Llama 3.3 70B on Groq)."""
    return os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")
