import requests
import feedparser
import os 


def search_semantic_scholar(query, limit=50, api_key=None):
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = "title,abstract,authors,year,venue,citationCount,externalIds"
    params = {"query": query, "limit": limit, "fields": fields}
    headers = {"x-api-key": api_key} if api_key else {}
    res = requests.get(base_url, params=params, headers=headers)
    if res.status_code == 429:
        print("Semantic Scholar: Rate limit exceeded. Register for an API key at https://www.semanticscholar.org/product/api#api-key-form")
        return res.json()
    elif res.status_code != 200:
        print(f"Semantic Scholar: Error {res.status_code} - {res.text}")
        return res.json()
    return res.json()

# parse arvix 
def search_arxiv(query):
    base_url = "http://export.arxiv.org/api/query"
    res = requests.get(f"{base_url}?search_query={query}&max_results=5")
    if res.status_code != 200:
        print(f"ArXiv: Error {res.status_code} - {res.text}")
        return ""
    return res.text

#format this arxiv data
def format_arxiv_results_and_download(xml_data, download_pdfs=False, output_dir="arxiv_pdfs"):
    feed = feedparser.parse(xml_data)
    output = f"ArXiv Search Results: {feed.feed.get('title', '')}\n"
    if download_pdfs and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    for entry in feed.entries:
        arxiv_id = entry.id.split('/abs/')[-1]  # get arXiv ID from URL
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        output += f"\nTitle: {entry.title}\n"
        output += f"Authors: {', '.join(author.name for author in entry.authors)}\n"
        output += f"Published: {entry.published}\n"
        output += f"arXiv Link: {entry.link}\n"
        output += f"PDF: {pdf_url}\n"
        output += f"Summary: {entry.summary[:300]}...\n"
        output += "-" * 80 + "\n"
        #download pdf 
        if download_pdfs:
            pdf_res = requests.get(pdf_url)
            if pdf_res.status_code == 200:
                filename = os.path.join(output_dir, f"{arxiv_id.replace('/', '_')}.pdf")
                with open(filename, "wb") as f:
                    f.write(pdf_res.content)
            else:
                print(f"Could not download PDF for {arxiv_id}")
    return output

# crossref lookup and formatting  to find metadata about a paper given its DOI
def search_crossref(doi):
    base_url = f"https://api.crossref.org/works/{doi}"
    res = requests.get(base_url)
    if res.status_code != 200:
        print(f"CrossRef: Error {res.status_code} - {res.text}")
        return {}
    return res.json()

def format_crossref_results(data):
    msg = data.get("message", {})
    output = f"Title: {msg.get('title', ['N/A'])[0]}\n"
    output += f"Journal: {msg.get('container-title', ['N/A'])[0]}\n"
    issued = msg.get("issued", {}).get("date-parts", [["N/A"]])[0]
    output += f"Published: {'-'.join(str(x) for x in issued)}\n"
    output += f"DOI: {msg.get('DOI','')}\n"
    output += f"Publisher: {msg.get('publisher','N/A')}\n"
    output += f"Citation Count: {msg.get('is-referenced-by-count','N/A')}\n"
    output += f"URL: {msg.get('URL','')}\n"
    authors = msg.get('author', [])
    if authors:
        output += "Authors: " + ", ".join(f"{a.get('given','')} {a.get('family','')}" for a in authors) + "\n"
    else:
        output += "Authors: N/A\n"
    return output

# MAIN 
if __name__ == "__main__":

    # arxiv returns the abstract of all papers related to copmputer vision 
    print("\nSearch: ArXiv")
    arxiv_raw = search_arxiv("computer vision")
    print(format_arxiv_results_and_download(arxiv_raw, download_pdfs=True))

    # cross-ref which takes in the DOI (unique identifier for paper's basically) and outputs their metadata like authors
    print("\nSearch: CrossRef")
    crossref_data = search_crossref("10.1038/s41586-019-1666-5")
    print(format_crossref_results(crossref_data))
