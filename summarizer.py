import os
from dotenv import load_dotenv
from groq import Groq
import fitz  # PyMuPDF

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")
        _client = Groq(api_key=api_key)
    return _client


def extract_full_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    text_parts = []

    for page in doc:
        text_parts.append(page.get_text())

    doc.close()
    return "\n".join(text_parts)


def summarize_paper(pdf_path: str) -> dict:
    text = extract_full_text(pdf_path)

    if not text.strip():
        return {
            "pdf": pdf_path,
            "summary": "No text content found in this PDF."
        }

    client = get_client()

    # Truncate if too long (Groq context limit)
    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Text truncated...]"

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": "You are a research assistant. Provide a comprehensive summary of this research paper. Include: 1) Main objective/problem, 2) Key methodology, 3) Main findings/results, 4) Conclusions. Keep it concise but informative (3-5 paragraphs)."
            },
            {
                "role": "user",
                "content": text
            }
        ],
        temperature=0.3,
        max_tokens=800
    )

    return {
        "pdf": pdf_path,
        "summary": response.choices[0].message.content
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
