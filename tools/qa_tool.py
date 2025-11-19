"""
Tool wrapper for Question Answering with RAG
"""
import sys
import os
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ChunkAndMap import PaperQAAgent, PaperChunk


class QATool:
    """
    Wrapper around PaperQAAgent for agent use
    Manages a single QA agent instance for the session
    """
    
    def __init__(self, llama_model_name: str = "meta-llama/Llama-3.2-1B"):
        self.agent = None
        self.model_name = llama_model_name
        self.current_paper_title = None
    
    def _ensure_agent(self):
        """Lazy load the QA agent"""
        if self.agent is None:
            print("\n🤖 Initializing QA Agent...")
            self.agent = PaperQAAgent(self.model_name)
    
    def chunk_text(self, pages_data: List[Dict], chunk_size: int = 400, overlap: int = 50) -> List[PaperChunk]:
        """
        Chunk text from pages
        
        Args:
            pages_data: List of page dicts from PDF extraction
            chunk_size: Size of each chunk
            overlap: Overlap between chunks
            
        Returns:
            List of PaperChunk objects
        """
        self._ensure_agent()
        return self.agent.chunk_text(pages_data, chunk_size, overlap)
    
    def index_paper(self, chunks: List[PaperChunk], paper_title: str = ""):
        """
        Index paper chunks into vector database
        
        Args:
            chunks: List of PaperChunk objects
            paper_title: Title of the paper
        """
        self._ensure_agent()
        self.agent.index_paper(chunks, paper_title)
        self.current_paper_title = paper_title
        print(f"✅ Indexed paper: {paper_title[:60]}...")
    
    def answer_question(self, question: str, top_k: int = 3) -> Dict[str, Any]:
        """
        Answer a question about the indexed paper
        
        Args:
            question: Question to answer
            top_k: Number of chunks to retrieve
            
        Returns:
            Dict with 'query', 'answer', 'sources'
        """
        self._ensure_agent()
        
        if not self.agent.collection:
            raise Exception("No paper indexed. Please index a paper first.")
        
        return self.agent.answer_question(question, top_k)
    
    def process_paper_and_answer(
        self, 
        pages_data: List[Dict], 
        paper_title: str,
        question: str,
        top_k: int = 3
    ) -> Dict[str, Any]:
        """
        Complete workflow: chunk → index → answer
        
        Args:
            pages_data: PDF pages data
            paper_title: Title of paper
            question: Question to answer
            top_k: Number of chunks to retrieve
            
        Returns:
            Answer dict with sources
        """
        chunks = self.chunk_text(pages_data)
        self.index_paper(chunks, paper_title)
        return self.answer_question(question, top_k)


# Singleton instance
_qa_tool_instance = None


def get_qa_tool() -> QATool:
    """
    Get or create singleton QATool instance
    """
    global _qa_tool_instance
    
    if _qa_tool_instance is None:
        _qa_tool_instance = QATool()
    
    return _qa_tool_instance
