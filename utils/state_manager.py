"""
State management for the question decomposition agent
"""
from typing import TypedDict, List, Dict, Optional, Literal
from dataclasses import dataclass, field
import sys
import os

# Import PaperMetadata from existing code
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ChunkAndMap import PaperMetadata


@dataclass
class SubQuestion:
    """
    Represents a sub-question decomposed from the original query
    """
    id: str
    text: str
    paper_needed: Optional[str] = None  # "BERT", "GPT-2", etc.
    status: Literal["pending", "searching", "answering", "complete", "failed"] = "pending"
    answer: Optional[str] = None
    sources: Optional[List[Dict]] = None
    paper_metadata: Optional[PaperMetadata] = None
    
    def __post_init__(self):
        if self.sources is None:
            self.sources = []


class AgentState(TypedDict):
    """
    State shared across all nodes in the agent graph
    """
    # User input
    original_query: str
    
    # Decomposition phase
    sub_questions: List[SubQuestion]
    
    # Paper management
    papers_cache: Dict[str, PaperMetadata]  # Key: paper title/id
    indexed_papers: Dict[str, str]  # Key: paper id, Value: pdf_path
    
    # Execution tracking
    current_sub_question_id: Optional[str]
    search_results: List[PaperMetadata]
    
    # Results
    sub_answers: Dict[str, str]  # Key: sub_question_id
    final_answer: Optional[str]
    
    # Error handling
    errors: List[str]
    retry_count: int


def create_initial_state(query: str) -> AgentState:
    """
    Create initial state from user query
    """
    return AgentState(
        original_query=query,
        sub_questions=[],
        papers_cache={},
        indexed_papers={},
        current_sub_question_id=None,
        search_results=[],
        sub_answers={},
        final_answer=None,
        errors=[],
        retry_count=0
    )


def get_current_question(state: AgentState) -> Optional[SubQuestion]:
    """
    Get the currently active sub-question
    """
    if not state['current_sub_question_id']:
        return None
    
    for sq in state['sub_questions']:
        if sq.id == state['current_sub_question_id']:
            return sq
    
    return None


def get_pending_questions(state: AgentState) -> List[SubQuestion]:
    """
    Get all pending sub-questions
    """
    return [sq for sq in state['sub_questions'] if sq.status == "pending"]


def get_completed_questions(state: AgentState) -> List[SubQuestion]:
    """
    Get all completed sub-questions
    """
    return [sq for sq in state['sub_questions'] if sq.status == "complete"]


def get_failed_questions(state: AgentState) -> List[SubQuestion]:
    """
    Get all failed sub-questions
    """
    return [sq for sq in state['sub_questions'] if sq.status == "failed"]
