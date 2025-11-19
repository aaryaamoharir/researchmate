"""
Agent nodes for the question decomposition workflow
"""
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.state_manager import AgentState, SubQuestion, get_current_question
from llm.llama_wrapper import get_llm
from llm.prompts import (
    DECOMPOSITION_PROMPT,
    SYNTHESIS_PROMPT,
    PAPER_RANKING_PROMPT,
    SEARCH_TERM_EXTRACTION_PROMPT
)
from tools.search_tool import get_search_tool
from tools.pdf_tool import get_pdf_tool
from tools.qa_tool import get_qa_tool


def decompose_question(state: AgentState) -> AgentState:
    """
    Decompose the original query into atomic sub-questions
    """
    print("\n" + "="*80)
    print("DECOMPOSITION NODE")
    print("="*80)
    
    llm = get_llm()
    query = state['original_query']
    
    print(f"\nOriginal Question: {query}")
    print("\nBreaking down into sub-questions...")
    
    # Generate sub-questions using LLM
    prompt = DECOMPOSITION_PROMPT.format(query=query)
    response = llm.generate_json(prompt, max_new_tokens=600)
    
    # Handle both list and dict responses
    if isinstance(response, dict) and 'sub_questions' in response:
        sub_questions_data = response['sub_questions']
    elif isinstance(response, list):
        sub_questions_data = response
    else:
        print("Failed to decompose question. Using original question as single sub-question.")
        sub_questions_data = [{"question": query, "paper_needed": None}]
    
    # Create SubQuestion objects
    sub_questions = []
    for i, sq_data in enumerate(sub_questions_data):
        sq = SubQuestion(
            id=f"sq_{i}",
            text=sq_data.get('question', ''),
            paper_needed=sq_data.get('paper_needed'),
            status="pending"
        )
        sub_questions.append(sq)
        print(f"\n  [{i+1}] {sq.text}")
        if sq.paper_needed:
            print(f"      → Paper needed: {sq.paper_needed}")
    
    state['sub_questions'] = sub_questions
    
    print(f"\n✅ Created {len(sub_questions)} sub-questions")
    
    return state


def search_papers(state: AgentState) -> AgentState:
    """
    Search for papers needed to answer current sub-question
    """
    print("\n" + "="*80)
    print("🔎 SEARCH NODE")
    print("="*80)
    
    current_q = get_current_question(state)
    if not current_q:
        state['errors'].append("No current question set")
        return state
    
    print(f"\nSub-question: {current_q.text}")
    
    # Determine search query
    if current_q.paper_needed:
        search_query = current_q.paper_needed
        print(f"Searching for specific paper: {search_query}")
    else:
        # Extract key terms from question
        llm = get_llm()
        prompt = SEARCH_TERM_EXTRACTION_PROMPT.format(question=current_q.text)
        search_query = llm.extract_text(prompt, max_new_tokens=50)
        print(f"Extracted search terms: {search_query}")
    
    # Search across APIs
    search_tool = get_search_tool()
    all_papers = search_tool.search_all(search_query)
    
    if not all_papers:
        current_q.status = "failed"
        state['errors'].append(f"No papers found for: {search_query}")
        print(f"\n No papers found")
        return state
    
    # Rank papers by relevance
    print(f"\n📊 Ranking {len(all_papers)} papers by relevance...")
    best_paper = rank_papers_for_question(all_papers, current_q.text)
    
    current_q.paper_metadata = best_paper
    state['papers_cache'][best_paper.title] = best_paper
    
    print(f"\nSelected: {best_paper.title[:80]}...")
    print(f"   Authors: {', '.join(best_paper.authors[:2])}")
    if best_paper.year:
        print(f"   Year: {best_paper.year}")
    
    return state


def rank_papers_for_question(papers, question: str):
    """
    Use LLM to rank papers and select most relevant
    """
    if len(papers) == 1:
        return papers[0]
    
    # Build papers list for prompt
    papers_list = []
    for i, paper in enumerate(papers[:5], 1):  # Limit to top 5
        papers_list.append(
            f"{i}. {paper.title}\n"
            f"   Authors: {', '.join(paper.authors[:3])}\n"
            f"   Year: {paper.year or 'N/A'}\n"
            f"   Abstract: {paper.abstract[:200] if paper.abstract else 'N/A'}..."
        )
    
    papers_text = "\n\n".join(papers_list)
    
    llm = get_llm()
    prompt = PAPER_RANKING_PROMPT.format(question=question, papers_list=papers_text)
    
    try:
        paper_num = llm.extract_number(prompt)
        if 1 <= paper_num <= len(papers[:5]):
            return papers[paper_num - 1]
    except:
        pass
    
    # Default to first paper if ranking fails
    return papers[0]


def download_and_index(state: AgentState) -> AgentState:
    """
    Download paper PDF, extract text, chunk, and index in vector DB
    """
    print("\n" + "="*80)
    print("⬇️  DOWNLOAD & INDEX NODE")
    print("="*80)
    
    current_q = get_current_question(state)
    if not current_q or not current_q.paper_metadata:
        state['errors'].append("No paper metadata available")
        return state
    
    paper = current_q.paper_metadata
    print(f"\nPaper: {paper.title[:80]}...")
    
    # Download PDF
    pdf_tool = get_pdf_tool()
    pdf_path = pdf_tool.download_pdf(paper)
    
    if not pdf_path:
        current_q.status = "failed"
        state['errors'].append(f"Failed to download: {paper.title}")
        print("\n Download failed")
        return state
    
    print(f"✓ Downloaded to: {pdf_path}")
    
    # Extract text
    pages_data = pdf_tool.extract_text(pdf_path)
    
    if not pages_data:
        current_q.status = "failed"
        state['errors'].append(f"Failed to extract text: {paper.title}")
        print("\n Text extraction failed")
        return state
    
    # Chunk and index
    qa_tool = get_qa_tool()
    chunks = qa_tool.chunk_text(pages_data, chunk_size=400, overlap=50)
    qa_tool.index_paper(chunks, paper_title=paper.title)
    
    # Cache the indexed paper
    state['indexed_papers'][paper.title] = pdf_path
    
    current_q.status = "answering"
    
    print(f"\n✅ Paper indexed and ready for Q&A")
    
    return state


def answer_question(state: AgentState) -> AgentState:
    """
    Answer the current sub-question using RAG
    """
    print("\n" + "="*80)
    print("💬 QA NODE")
    print("="*80)
    
    current_q = get_current_question(state)
    if not current_q:
        state['errors'].append("No current question set")
        return state
    
    print(f"\nQuestion: {current_q.text}")
    
    # Get answer using RAG
    qa_tool = get_qa_tool()
    
    try:
        result = qa_tool.answer_question(current_q.text, top_k=3)
        
        current_q.answer = result['answer']
        current_q.sources = result['sources']
        current_q.status = "complete"
        
        state['sub_answers'][current_q.id] = result['answer']
        
        print(f"\nAnswer generated:")
        print(f"   {result['answer'][:150]}...")
        
    except Exception as e:
        current_q.status = "failed"
        state['errors'].append(f"QA failed: {str(e)}")
        print(f"\n QA failed: {e}")
    
    return state


def synthesize_answer(state: AgentState) -> AgentState:
    """
    Combine all sub-answers into final coherent response
    """
    print("\n" + "="*80)
    print(" SYNTHESIS NODE")
    print("="*80)
    
    # Build context from all sub-answers
    context_parts = []
    for sq in state['sub_questions']:
        if sq.status == "complete" and sq.answer:
            paper_name = sq.paper_metadata.title if sq.paper_metadata else "Unknown"
            context_parts.append(
                f"Q: {sq.text}\n"
                f"A: {sq.answer}\n"
                f"Source: [{paper_name[:60]}...]"
            )
    
    if not context_parts:
        state['final_answer'] = "Unable to generate answer - no sub-questions were answered successfully."
        return state
    
    context = "\n\n".join(context_parts)
    
    print(f"\nSynthesizing {len(context_parts)} sub-answers...")
    
    # Generate final answer
    llm = get_llm()
    prompt = SYNTHESIS_PROMPT.format(
        original_query=state['original_query'],
        sub_answers=context
    )
    
    final_answer = llm.generate(prompt, max_new_tokens=800, temperature=0.7)
    state['final_answer'] = final_answer
    
    print(f"\nFinal answer generated ({len(final_answer)} chars)")
    
    return state
