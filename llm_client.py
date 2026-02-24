"""Shared LLM client helpers for OpenAI-compatible providers (DeepSeek).

This centralizes API key lookup, base URL configuration, and model defaults so
callers (agent, answer_agent, summarizer) do not drift over time.
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


def get_deepseek_client() -> OpenAI:
    """Return a singleton OpenAI client configured for DeepSeek.

    Transition behavior: if `DEEPSEEK_API_KEY` is absent, temporarily fall back to
    `GROQ_API_KEY` so migration can happen in phases. This fallback should be
    removed after cutover.
    """
    global _client

    if _client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "Missing API key. Set DEEPSEEK_API_KEY (preferred) or GROQ_API_KEY "
                "during the migration transition."
            )
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


def get_chat_model() -> str:
    """Return the configured chat model (defaults to DeepSeek chat)."""
    return os.environ.get("DEEPSEEK_CHAT_MODEL", "deepseek-chat")
