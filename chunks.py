import fitz  # PyMuPDF


def extract_text_chunks(pdf_path: str, chunk_size: int = 500, overlap: int = 50) -> list[dict]:
    doc = fitz.open(pdf_path)
    chunks = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()

        if not text.strip():
            continue

        # Split page text into chunks
        start = 0
        while start < len(text):
            end = start + chunk_size

            # Try to break at sentence or paragraph
            if end < len(text):
                # Look for paragraph break
                para_break = text.rfind('\n\n', start, end)
                if para_break > start + chunk_size // 2:
                    end = para_break
                else:
                    # Look for sentence break
                    for sep in ['. ', '.\n', '? ', '!\n']:
                        sent_break = text.rfind(sep, start, end)
                        if sent_break > start + chunk_size // 2:
                            end = sent_break + 1
                            break

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "page": page_num + 1,
                    "pdf": pdf_path,
                    "type": "text"
                })

            start = end - overlap if end < len(text) else len(text)

    doc.close()
    return chunks
