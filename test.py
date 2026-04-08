from MCPservers.app.tools.supabase import supabase_sql
from MCPservers.app.main import get_paper, create_paper, create_summary, get_summary, get_pdf_page_urls, get_pdf_page_url
from MCPservers.app.tools.googlescholar import search_research
import json

# result = create_summary(
#     pdf_id=19,
#     summary="This paper explores attention mechanisms in transformer architectures."
# )
# print("create_summary result:", result)

# # Test get_summary
# result = get_summary(19)
# print("get_summary result:", result)

# result = get_pdf_page_urls(30)
# for page in result:
#     print(page["url"])

# result = get_pdf_page_url(pdf_id=30, page_number=1)
# print(result)


#test for google scholar
results = search_research(
        "transformer attention mechanisms",
        total_results=10,
        date_restrict="y1",   # last year
        prefer_pdfs=True
    )
print(f"Fetched {len(results)} results")
print(json.dumps(results, indent=2, ensure_ascii=False))