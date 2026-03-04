from MCPservers.app.tools.supabase import supabase_sql
from MCPservers.app.main import get_paper, create_paper, create_summary, get_summary


result = create_summary(
    pdf_id=19,
    summary="This paper explores attention mechanisms in transformer architectures."
)
print("create_summary result:", result)

# Test get_summary
result = get_summary(19)
print("get_summary result:", result)