import requests
import feedparser
import os

# ---------- ARXIV HELPERS ----------
def search_arxiv(query, max_results=5):
    """Search ArXiv using a query string."""
    base_url = "http://export.arxiv.org/api/query"
    res = requests.get(f"{base_url}?search_query=all:{query}&max_results={max_results}")
    if res.status_code != 200:
        print(f"ArXiv: Error {res.status_code} - {res.text}")
        return ""
    return res.text


def format_arxiv_results_and_download(xml_data, download_pdfs=False, output_dir="arxiv_pdfs"):
    """Format ArXiv results and optionally download PDFs."""
    feed = feedparser.parse(xml_data)
    output = ""
    if download_pdfs and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for entry in feed.entries:
        arxiv_id = entry.id.split('/abs/')[-1]
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        output += f"\nTitle: {entry.title}\n"
        output += f"Authors: {', '.join(author.name for author in entry.authors)}\n"
        output += f"Published: {entry.published}\n"
        output += f"arXiv Link: {entry.link}\n"
        output += f"PDF: {pdf_url}\n"
        output += f"Summary: {entry.summary[:300]}...\n"
        output += "-" * 80 + "\n"

        if download_pdfs:
            pdf_res = requests.get(pdf_url)
            if pdf_res.status_code == 200:
                filename = os.path.join(output_dir, f"{arxiv_id.replace('/', '_')}.pdf")
                with open(filename, "wb") as f:
                    f.write(pdf_res.content)
                print(f"✅ Downloaded: {filename}")
            else:
                print(f"⚠️ Could not download PDF for {arxiv_id}")
    return output


# ---------- CROSSREF HELPERS ----------
def search_crossref_title(title):
    """Search for a paper by title and return its DOI and metadata."""
    url = f"https://api.crossref.org/works?query.title={title}&rows=1"
    res = requests.get(url)
    if res.status_code != 200:
        print(f"CrossRef: Error {res.status_code} - {res.text}")
        return None
    data = res.json()
    items = data.get("message", {}).get("items", [])
    return items[0] if items else None


def get_references_from_doi(doi):
    """Get reference list for a given DOI from CrossRef."""
    base_url = f"https://api.crossref.org/works/{doi}"
    res = requests.get(base_url)
    if res.status_code != 200:
        print(f"CrossRef: Error {res.status_code} - {res.text}")
        return []
    data = res.json()
    return data.get("message", {}).get("reference", [])


def download_main_pdf(doi, title, output_dir="main_paper"):
    """Try downloading the main paper PDF using DOI or ArXiv."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Try direct DOI-based PDF download first
    pdf_url = f"https://doi.org/{doi}"
    try:
        response = requests.get(pdf_url, allow_redirects=True)
        if "pdf" in response.headers.get("Content-Type", ""):
            filename = os.path.join(output_dir, f"{title[:50].replace('/', '_')}.pdf")
            with open(filename, "wb") as f:
                f.write(response.content)
            print(f"✅ Downloaded main paper PDF: {filename}")
            return
    except Exception:
        pass

    # Otherwise, search on ArXiv
    print("⚠️ Could not download from DOI. Trying ArXiv...")
    xml_data = search_arxiv(title)
    if xml_data:
        format_arxiv_results_and_download(xml_data, download_pdfs=True, output_dir=output_dir)
    else:
        print("❌ Could not find main paper on ArXiv.")


def format_reference(ref):
    """Nicely format one reference entry."""
    title = ref.get("article-title") or ref.get("series-title") or ref.get("volume-title") or "N/A"
    doi = ref.get("DOI", "N/A")
    author = ref.get("author", "N/A")
    year = ref.get("year", "N/A")
    return f"Title: {title}\nAuthor: {author}\nYear: {year}\nDOI: {doi}\n"


# ---------- MAIN ----------
if __name__ == "__main__":
    title_to_search = input("Enter the paper title: ").strip()

    # Step 1: Search paper by title and get DOI
    print("\n🔍 Searching CrossRef for paper...")
    paper_data = search_crossref_title(title_to_search)
    if not paper_data:
        print("❌ No paper found with that title.")
        exit()

    doi = paper_data.get("DOI", None)
    title = paper_data.get("title", ["N/A"])[0]
    if not doi:
        print("❌ No DOI found for this paper.")
        exit()

    print(f"\n✅ Found paper: {title}")
    print(f"DOI: {doi}")

    # Step 2: Download the main paper’s PDF
    print("\n⬇️ Downloading main paper PDF...")
    download_main_pdf(doi, title)

    # Step 3: Get all reference papers
    print("\n📚 Extracting references from this paper...")
    refs = get_references_from_doi(doi)
    if not refs:
        print("❌ No references found.")
        exit()

    print(f"\nFound {len(refs)} references.\n" + "=" * 80)
    for i, ref in enumerate(refs, 1):
        print(f"\nReference {i}:\n{format_reference(ref)}")

        # Optional: if reference DOI exists, search on arXiv
        if "DOI" in ref:
            arxiv_data = search_arxiv(ref["DOI"])
            if arxiv_data:
                print(format_arxiv_results_and_download(arxiv_data, download_pdfs=False))

