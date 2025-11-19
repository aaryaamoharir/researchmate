"""
Tool wrapper for paper search across multiple APIs
"""
import sys
import os
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ChunkAndMap import PaperSearchAPI, PaperMetadata


class SearchTool:
    """
    Wrapper around PaperSearchAPI for agent use
    """
    
    def __init__(self, semantic_scholar_api_key=None):
        self.api = PaperSearchAPI(semantic_scholar_api_key)
    
    def search_all(self, query: str) -> List[PaperMetadata]:
        """
        Search across all APIs and return flattened list of papers
        
        Args:
            query: Search query string
            
        Returns:
            List of PaperMetadata objects from all sources
        """
        print(f"\n🔍 Searching for: '{query}'")
        results = self.api.search_all(query)
        
        # Flatten results from all sources
        all_papers = []
        for source, papers in results.items():
            all_papers.extend(papers)
        
        print(f"✓ Found {len(all_papers)} total papers")
        return all_papers
    
    def search_arxiv(self, query: str, max_results: int = 10) -> List[PaperMetadata]:
        """
        Search only arXiv
        """
        return self.api.search_arxiv(query, max_results)
    
    def search_semantic_scholar(self, query: str, limit: int = 10) -> List[PaperMetadata]:
        """
        Search only Semantic Scholar
        """
        return self.api.search_semantic_scholar(query, limit)
    
    def search_crossref(self, title: str) -> PaperMetadata:
        """
        Search CrossRef by paper title
        """
        return self.api.search_crossref(title)


# Singleton instance
_search_tool_instance = None


def get_search_tool() -> SearchTool:
    """
    Get or create singleton SearchTool instance
    """
    global _search_tool_instance
    
    if _search_tool_instance is None:
        _search_tool_instance = SearchTool()
    
    return _search_tool_instance
