from __future__ import annotations

import fitz  # PyMuPDF
from dotenv import load_dotenv

from llm_client import get_chat_model, get_groq_client

load_dotenv()

MAX_SUMMARY_CHARS = 50000


def extract_full_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    text_parts = []

    for page in doc:
        text_parts.append(page.get_text())

    doc.close()
    return "\n".join(text_parts)


def _truncate_text(text: str, max_chars: int = MAX_SUMMARY_CHARS) -> str:
    """Char-based truncation fallback. Token-aware truncation can be added later."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[Text truncated...]"


def summarize_paper(pdf_path: str) -> dict:
    text = extract_full_text(pdf_path)

    if not text.strip():
        return {
            "pdf": pdf_path,
            "summary": "No text content found in this PDF.",
        }

    client = get_groq_client()
    text = _truncate_text(text)

    response = client.chat.completions.create(
        model=get_chat_model(),
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a research assistant. Provide a comprehensive summary "
                    "of this research paper. Include: 1) Main objective/problem, "
                    "2) Key methodology, 3) Main findings/results, 4) Conclusions. "
                    "Keep it concise but informative (3-5 paragraphs)."
                ),
            },
            {
                "role": "user",
                "content": text,
            },
        ],
        temperature=0.3,
        max_tokens=800,
    )

    return {
        "pdf": pdf_path,
        "summary": response.choices[0].message.content,
    }


# CLI for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python summarizer.py <pdf_path>")
        sys.exit(1)

    result = summarize_paper(sys.argv[1])
    print(f"\nPDF: {result['pdf']}\n")
    print(f"Summary:\n{result['summary']}")
