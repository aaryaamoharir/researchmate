"""
Tool wrapper for PDF download and text extraction
"""
import sys
import os
from typing import List, Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ChunkAndMap import PDFManager, PaperMetadata


class PDFTool:
    """
    Wrapper around PDFManager for agent use
    """
    
    def __init__(self, output_dir: str = "downloaded_papers"):
        self.manager = PDFManager(output_dir)
    
    def download_pdf(self, paper: PaperMetadata) -> Optional[str]:
        """
        Download PDF for a paper
        
        Args:
            paper: PaperMetadata object with pdf_url
            
        Returns:
            Path to downloaded PDF, or None if failed
        """
        return self.manager.download_pdf(paper)
    
    def extract_text(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract text from PDF with page numbers
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of dicts with 'page_num', 'text', 'char_count'
        """
        return self.manager.extract_text_from_pdf(pdf_path)
    
    def download_and_extract(self, paper: PaperMetadata) -> Optional[List[Dict[str, Any]]]:
        """
        Download PDF and extract text in one call
        
        Args:
            paper: PaperMetadata object
            
        Returns:
            List of page data, or None if download failed
        """
        pdf_path = self.download_pdf(paper)
        if not pdf_path:
            return None
        
        return self.extract_text(pdf_path)


# Singleton instance
_pdf_tool_instance = None


def get_pdf_tool() -> PDFTool:
    """
    Get or create singleton PDFTool instance
    """
    global _pdf_tool_instance
    
    if _pdf_tool_instance is None:
        _pdf_tool_instance = PDFTool()
    
    return _pdf_tool_instance
