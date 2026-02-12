
import fitz  # PyMuPDF
from PIL import Image
import io


def extract_figures(pdf_path: str, min_size: int = 100) -> list[dict]:
    """Extract embedded images/figures from PDF.

    Args:
        pdf_path: Path to the PDF file
        min_size: Minimum width/height to include (filters out icons)

    Returns:
        List of figure dicts with image, page, and metadata
    """
    doc = fitz.open(pdf_path)
    figures = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images()

        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]

            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                img = Image.open(io.BytesIO(image_bytes))

                # Filter out small images (icons, bullets, etc.)
                if img.width >= min_size and img.height >= min_size:
                    # Convert to RGB if necessary
                    if img.mode != "RGB":
                        img = img.convert("RGB")

                    figures.append({
                        "image": img,
                        "page": page_num + 1,
                        "pdf": pdf_path,
                        "type": "figure",
                        "size": (img.width, img.height)
                    })
            except Exception:
                # Skip images that can't be extracted
                continue

    doc.close()
    return figures


def extract_page_as_image(pdf_path: str, page_num: int) -> Image.Image:
    """Extract a specific page as an image (fallback for complex layouts).

    Args:
        pdf_path: Path to the PDF file
        page_num: Page number (1-indexed)

    Returns:
        PIL Image of the page
    """
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    doc.close()
    return img
