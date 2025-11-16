"""
Unified Paper Search & Q&A Agent
Combines arXiv, Semantic Scholar, CrossRef + Local Llama Q&A with Source Attribution

Installation:
pip install torch transformers sentence-transformers chromadb PyPDF2 feedparser requests

Usage:
python unified_paper_agent.py
"""

import requests
import feedparser
import os
import PyPDF2
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


# ==================== DATA MODELS ====================
@dataclass
class PaperMetadata:
    """Stores paper metadata from various sources"""
    title: str
    authors: List[str]
    abstract: str = ""
    year: Optional[int] = None
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    pdf_url: Optional[str] = None
    citation_count: int = 0
    venue: str = ""
    source: str = ""  # "arxiv", "semantic_scholar", "crossref"


@dataclass
class PaperChunk:
    """Represents a chunk of text from a paper with metadata"""
    text: str
    page_num: int
    chunk_id: str
    section: str = ""
    paper_title: str = ""


# ==================== API SEARCH FUNCTIONS ====================
class PaperSearchAPI:
    """Unified API for searching papers across multiple sources"""
    
    def __init__(self, semantic_scholar_api_key: Optional[str] = None):
        self.ss_api_key = semantic_scholar_api_key
    
    # ---------- SEMANTIC SCHOLAR ----------
    def search_semantic_scholar(self, query: str, limit: int = 10) -> List[PaperMetadata]:
        """Search Semantic Scholar API"""
        base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
        fields = "title,abstract,authors,year,venue,citationCount,externalIds"
        params = {"query": query, "limit": limit, "fields": fields}
        headers = {"x-api-key": self.ss_api_key} if self.ss_api_key else {}
        
        try:
            res = requests.get(base_url, params=params, headers=headers, timeout=10)
            if res.status_code == 429:
                print("⚠️  Semantic Scholar rate limit. Get API key: https://www.semanticscholar.org/product/api")
                return []
            if res.status_code != 200:
                print(f"⚠️  Semantic Scholar Error: {res.status_code}")
                return []
            
            data = res.json()
            papers = []
            
            for paper in data.get("data", []):
                authors = [a.get("name", "Unknown") for a in paper.get("authors", [])]
                external_ids = paper.get("externalIds", {})
                
                papers.append(PaperMetadata(
                    title=paper.get("title", "N/A"),
                    authors=authors,
                    abstract=paper.get("abstract", ""),
                    year=paper.get("year"),
                    arxiv_id=external_ids.get("ArXiv"),
                    doi=external_ids.get("DOI"),
                    pdf_url=f"https://arxiv.org/pdf/{external_ids.get('ArXiv')}.pdf" if external_ids.get("ArXiv") else None,
                    citation_count=paper.get("citationCount", 0),
                    venue=paper.get("venue", ""),
                    source="semantic_scholar"
                ))
            
            print(f"✓ Found {len(papers)} papers from Semantic Scholar")
            return papers
        except Exception as e:
            print(f"⚠️  Semantic Scholar error: {e}")
            return []
    
    # ---------- ARXIV ----------
    def search_arxiv(self, query: str, max_results: int = 10) -> List[PaperMetadata]:
        """Search arXiv API"""
        base_url = "http://export.arxiv.org/api/query"
        
        try:
            res = requests.get(f"{base_url}?search_query=all:{query}&max_results={max_results}", timeout=10)
            
            if res.status_code != 200:
                print(f"⚠️  ArXiv Error: {res.status_code}")
                return []
            
            feed = feedparser.parse(res.text)
            papers = []
            
            for entry in feed.entries:
                arxiv_id = entry.id.split('/abs/')[-1]
                authors = [author.name for author in entry.authors]
                
                papers.append(PaperMetadata(
                    title=entry.title,
                    authors=authors,
                    abstract=entry.summary,
                    year=int(entry.published[:4]) if entry.published else None,
                    arxiv_id=arxiv_id,
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                    source="arxiv"
                ))
            
            print(f"✓ Found {len(papers)} papers from arXiv")
            return papers
        except Exception as e:
            print(f"⚠️  ArXiv error: {e}")
            return []
    
    # ---------- CROSSREF ----------
    def search_crossref(self, title: str) -> Optional[PaperMetadata]:
        """Search CrossRef by title"""
        try:
            url = f"https://api.crossref.org/works?query.title={title}&rows=1"
            res = requests.get(url, timeout=10)
            
            if res.status_code != 200:
                print(f"⚠️  CrossRef Error: {res.status_code}")
                return None
            
            data = res.json()
            items = data.get("message", {}).get("items", [])
            
            if not items:
                return None
            
            paper = items[0]
            authors_data = paper.get("author", [])
            authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_data]
            
            issued = paper.get("issued", {}).get("date-parts", [[None]])[0]
            year = issued[0] if issued else None
            
            result = PaperMetadata(
                title=paper.get("title", ["N/A"])[0],
                authors=authors,
                abstract=paper.get("abstract", ""),
                year=year,
                doi=paper.get("DOI"),
                citation_count=paper.get("is-referenced-by-count", 0),
                venue=paper.get("container-title", [""])[0],
                source="crossref"
            )
            
            print(f"✓ Found paper from CrossRef")
            return result
        except Exception as e:
            print(f"⚠️  CrossRef error: {e}")
            return None
    
    def get_references_from_doi(self, doi: str) -> List[Dict]:
        """Get references from a paper using its DOI"""
        try:
            url = f"https://api.crossref.org/works/{doi}"
            res = requests.get(url, timeout=10)
            
            if res.status_code != 200:
                return []
            
            data = res.json()
            return data.get("message", {}).get("reference", [])
        except Exception as e:
            print(f"⚠️  Error getting references: {e}")
            return []
    
    # ---------- UNIFIED SEARCH ----------
    def search_all(self, query: str) -> Dict[str, List[PaperMetadata]]:
        """Search across all APIs and return results"""
        print(f"\n🔍 Searching all sources for: '{query}'")
        print("="*80)
        
        results = {
            "semantic_scholar": [],
            "arxiv": [],
            "crossref": []
        }
        
        # Search Semantic Scholar
        print("\n📚 Searching Semantic Scholar...")
        results["semantic_scholar"] = self.search_semantic_scholar(query, limit=5)
        
        # Search arXiv
        print("\n📄 Searching arXiv...")
        results["arxiv"] = self.search_arxiv(query, max_results=5)
        
        # Search CrossRef (only if query looks like a title)
        if len(query.split()) > 3:  # Likely a title
            print("\n🔗 Searching CrossRef...")
            crossref_result = self.search_crossref(query)
            if crossref_result:
                results["crossref"] = [crossref_result]
        
        return results


# ==================== PDF MANAGEMENT ====================
class PDFManager:
    """Handles PDF downloading and text extraction"""
    
    def __init__(self, output_dir: str = "downloaded_papers"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"✓ Created directory: {output_dir}")
    
    def download_pdf(self, paper: PaperMetadata) -> Optional[str]:
        """Download PDF from paper metadata"""
        if not paper.pdf_url:
            print(f"⚠️  No PDF URL for: {paper.title[:50]}")
            return None
        
        filename = self._sanitize_filename(paper.title)
        filepath = os.path.join(self.output_dir, filename)
        
        # Skip if already downloaded
        if os.path.exists(filepath):
            print(f"✓ Already downloaded: {filename}")
            return filepath
        
        try:
            print(f"⬇️  Downloading: {paper.title[:50]}...")
            response = requests.get(paper.pdf_url, timeout=30)
            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print(f"✅ Downloaded: {filename}")
                return filepath
            else:
                print(f"❌ Download failed ({response.status_code}): {paper.title[:50]}")
                return None
        except Exception as e:
            print(f"❌ Error downloading {paper.title[:50]}: {e}")
            return None
    
    def _sanitize_filename(self, title: str) -> str:
        """Create safe filename from title"""
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        return f"{safe_title[:100]}.pdf"
    
    def extract_text_from_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract text from PDF with page numbers"""
        pages_data = []
        
        try:
            print(f"📖 Extracting text from: {os.path.basename(pdf_path)}")
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                for page_num, page in enumerate(pdf_reader.pages, start=1):
                    text = page.extract_text()
                    if text.strip():
                        pages_data.append({
                            'page_num': page_num,
                            'text': text,
                            'char_count': len(text)
                        })
            
            print(f"✓ Extracted {len(pages_data)} pages from PDF")
            return pages_data
        except Exception as e:
            print(f"❌ Error extracting text: {e}")
            return []


# ==================== LLAMA MODEL ====================
class LlamaModel:
    """Wrapper for local Llama model"""
    
    def __init__(self, model_name="meta-llama/Llama-3.2-1B"):
        print(f"\n🤖 Loading Llama model: {model_name}...")
        print("   This may take a few minutes on first run...")
        
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype="auto",
                device_map="auto"
            )
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            print(f"✅ Llama model loaded on {self.model.device}")
        except Exception as e:
            print(f"❌ Error loading Llama model: {e}")
            print("\nMake sure you have:")
            print("1. Installed transformers: pip install transformers")
            print("2. Installed torch: pip install torch")
            print("3. Accepted the model license on HuggingFace")
            raise
    
    def generate(self, prompt: str, max_new_tokens=500, temperature=0.7) -> str:
        """Generate text using Llama"""
        try:
            inputs = self.tokenizer(
                prompt, 
                return_tensors="pt", 
                truncation=True, 
                max_length=2048
            ).to(self.model.device)
            
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=0.9,
                do_sample=True,
                pad_token_id=self.tokenizer.pad_token_id
            )
            
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Remove the prompt from the response
            if response.startswith(prompt):
                response = response[len(prompt):].strip()
            
            return response
        except Exception as e:
            return f"Error generating response: {e}"


# ==================== Q&A AGENT ====================
class PaperQAAgent:
    """Agent for answering questions about papers with source attribution"""
    
    def __init__(self, llama_model_name="meta-llama/Llama-3.2-1B"):
        try:
            from sentence_transformers import SentenceTransformer
            import chromadb
            
            print("\n" + "="*80)
            print("Initializing Paper Q&A Agent")
            print("="*80)
            
            # Load embedding model for retrieval
            print("\n📊 Loading embedding model (all-MiniLM-L6-v2)...")
            self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
            print("✓ Embedding model loaded")
            
            # Initialize ChromaDB
            self.chroma_client = chromadb.Client()
            self.collection = None
            self.chunks = []
            
            # Load Llama model for generation
            self.llm = LlamaModel(llama_model_name)
            
            print("\n✅ Paper Q&A Agent ready!")
            
        except ImportError as e:
            print(f"\n❌ Missing dependency: {e}")
            print("\nPlease install required packages:")
            print("pip install sentence-transformers chromadb transformers torch")
            raise
    
    def chunk_text(self, pages_data: List[Dict], chunk_size=400, overlap=50) -> List[PaperChunk]:
        """Split text into overlapping chunks with metadata"""
        print(f"\n✂️  Chunking text (chunk_size={chunk_size}, overlap={overlap})...")
        chunks = []
        chunk_counter = 0
        
        for page_data in pages_data:
            text = page_data['text']
            page_num = page_data['page_num']
            sentences = text.split('. ')
            
            current_chunk = ""
            for sentence in sentences:
                if len(current_chunk) + len(sentence) < chunk_size:
                    current_chunk += sentence + ". "
                else:
                    if current_chunk.strip():
                        chunks.append(PaperChunk(
                            text=current_chunk.strip(),
                            page_num=page_num,
                            chunk_id=f"chunk_{chunk_counter}",
                            section=self._detect_section(current_chunk)
                        ))
                        chunk_counter += 1
                    
                    # Add overlap
                    words = current_chunk.split()
                    overlap_text = ' '.join(words[-overlap//5:]) if len(words) > overlap//5 else ""
                    current_chunk = overlap_text + " " + sentence + ". "
            
            # Add remaining text
            if current_chunk.strip():
                chunks.append(PaperChunk(
                    text=current_chunk.strip(),
                    page_num=page_num,
                    chunk_id=f"chunk_{chunk_counter}",
                    section=self._detect_section(current_chunk)
                ))
                chunk_counter += 1
        
        print(f"✓ Created {len(chunks)} chunks")
        return chunks
    
    def _detect_section(self, text: str) -> str:
        """Detect section from text"""
        text_lower = text.lower()[:100]
        sections = {
            "abstract": "Abstract",
            "introduction": "Introduction",
            "method": "Methods",
            "result": "Results",
            "discussion": "Discussion",
            "conclusion": "Conclusion",
            "reference": "References"
        }
        for keyword, section in sections.items():
            if keyword in text_lower:
                return section
        return "Content"
    
    def index_paper(self, chunks: List[PaperChunk], paper_title: str = ""):
        """Index paper chunks into ChromaDB vector database"""
        print(f"\n🗄️  Indexing paper into vector database...")
        self.chunks = chunks
        
        # Delete existing collection if any
        try:
            self.chroma_client.delete_collection("papers")
        except:
            pass
        
        # Create new collection
        self.collection = self.chroma_client.create_collection("papers")
        
        # Generate embeddings for all chunks
        print("   Generating embeddings for chunks...")
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedder.encode(texts, show_progress_bar=True).tolist()
        
        # Prepare metadata
        metadatas = [{
            "page_num": chunk.page_num,
            "chunk_id": chunk.chunk_id,
            "section": chunk.section,
            "paper_title": paper_title
        } for chunk in chunks]
        
        # Add to ChromaDB
        self.collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=[chunk.chunk_id for chunk in chunks]
        )
        
        print(f"✅ Indexed {len(chunks)} chunks into ChromaDB")
    
    def retrieve_relevant_chunks(self, query: str, top_k: int = 3) -> List[Dict]:
        """Retrieve most relevant chunks for a query using vector search"""
        if not self.collection:
            raise Exception("No paper indexed. Please index a paper first.")
        
        # Embed the query
        query_embedding = self.embedder.encode([query])[0].tolist()
        
        # Search in ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding], 
            n_results=top_k
        )
        
        # Format results
        retrieved = []
        for i in range(len(results['ids'][0])):
            retrieved.append({
                'chunk_id': results['ids'][0][i],
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i] if 'distances' in results else None
            })
        
        return retrieved
    
    def answer_question(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        """Answer a question about the paper with source attribution"""
        print(f"\n{'='*80}")
        print(f"Processing question: {query}")
        print('='*80)
        
        # Step 1: Retrieve relevant chunks
        print(f"\n🔍 Retrieving top {top_k} relevant chunks...")
        retrieved = self.retrieve_relevant_chunks(query, top_k)
        
        for i, chunk in enumerate(retrieved, 1):
            print(f"   {i}. Page {chunk['metadata']['page_num']}, Section: {chunk['metadata']['section']}")
        
        # Step 2: Build context for Llama
        context_parts = []
        for i, chunk in enumerate(retrieved):
            context_parts.append(
                f"[Source {i+1} - Page {chunk['metadata']['page_num']}, "
                f"Section: {chunk['metadata']['section']}]\n{chunk['text']}"
            )
        context = "\n\n".join(context_parts)
        
        # Step 3: Create prompt with citation instructions
        prompt = f"""You are a helpful research assistant. Answer the question based on the paper excerpts below.

IMPORTANT INSTRUCTIONS:
1. Use ONLY information from the provided sources
2. Cite sources using [Source N] notation (e.g., [Source 1], [Source 2])
3. Be concise and accurate
4. If the sources don't contain enough information to answer fully, say so

Paper Excerpts:
{context}

Question: {query}

Answer:"""
        
        # Step 4: Generate answer with Llama
        print("\n🤖 Generating answer with Llama...")
        answer = self.llm.generate(prompt, max_new_tokens=300, temperature=0.7)
        
        # Step 5: Return structured response
        return {
            'query': query,
            'answer': answer,
            'sources': [{
                'source_id': i+1,
                'page': chunk['metadata']['page_num'],
                'section': chunk['metadata']['section'],
                'text_preview': chunk['text'][:200] + "...",
                'full_text': chunk['text'],
                'relevance_score': 1 - chunk['distance'] if chunk['distance'] else None
            } for i, chunk in enumerate(retrieved)]
        }


# ==================== MAIN APPLICATION ====================
def print_header():
    """Print application header"""
    print("\n" + "="*80)
    print(" " * 20 + "📚 UNIFIED PAPER SEARCH & Q&A AGENT")
    print("="*80)
    print("\nFeatures:")
    print("  ✓ Search across arXiv, Semantic Scholar, and CrossRef")
    print("  ✓ Download papers automatically")
    print("  ✓ Ask questions with source attribution")
    print("  ✓ Powered by local Llama model + ChromaDB")
    print("="*80)


def display_papers(all_papers: List[PaperMetadata]):
    """Display list of papers"""
    print(f"\n{'='*80}")
    print(f"FOUND {len(all_papers)} PAPERS")
    print('='*80)
    
    for i, paper in enumerate(all_papers, 1):
        print(f"\n[{i}] {paper.title}")
        print(f"    Authors: {', '.join(paper.authors[:3])}" + (" et al." if len(paper.authors) > 3 else ""))
        if paper.year:
            print(f"    Year: {paper.year}")
        if paper.citation_count:
            print(f"    Citations: {paper.citation_count}")
        if paper.venue:
            print(f"    Venue: {paper.venue}")
        print(f"    Source: {paper.source}")


def main():
    """Interactive paper search and Q&A system"""
    
    print_header()
    
    # Initialize components
    print("\n🚀 Initializing system...")
    search_api = PaperSearchAPI()
    pdf_manager = PDFManager()
    
    # Step 1: Search for papers
    print("\n" + "="*80)
    print("STEP 1: SEARCH FOR PAPERS")
    print("="*80)
    query = input("\n🔍 Enter search query (paper topic or title): ").strip()
    
    if not query:
        print("❌ No query provided. Exiting.")
        return
    
    results = search_api.search_all(query)
    
    # Collect all papers
    all_papers = []
    for source, papers in results.items():
        all_papers.extend(papers)
    
    if not all_papers:
        print("\n❌ No papers found. Try a different query.")
        return
    
    # Display results
    display_papers(all_papers)
    
    # Step 2: Select paper to analyze
    print("\n" + "="*80)
    print("STEP 2: SELECT PAPER")
    print("="*80)
    choice = input(f"\nSelect paper number (1-{len(all_papers)}) or 'q' to quit: ").strip()
    
    if choice.lower() == 'q':
        print("\n👋 Goodbye!")
        return
    
    try:
        selected_idx = int(choice) - 1
        if selected_idx < 0 or selected_idx >= len(all_papers):
            raise ValueError
        selected_paper = all_papers[selected_idx]
    except (ValueError, IndexError):
        print("❌ Invalid selection. Exiting.")
        return
    
    print(f"\n✅ Selected: {selected_paper.title}")
    
    # Step 3: Download PDF
    print("\n" + "="*80)
    print("STEP 3: DOWNLOAD PDF")
    print("="*80)
    
    pdf_path = pdf_manager.download_pdf(selected_paper)
    
    if not pdf_path:
        print("\n❌ Could not download PDF. Exiting.")
        return
    
    # Step 4: Initialize Q&A agent and index paper
    print("\n" + "="*80)
    print("STEP 4: INITIALIZE Q&A AGENT")
    print("="*80)
    
    try:
        qa_agent = PaperQAAgent(llama_model_name="meta-llama/Llama-3.2-1B")
    except Exception as e:
        print(f"\n❌ Failed to initialize Q&A agent: {e}")
        return
    
    # Extract text from PDF
    pages = pdf_manager.extract_text_from_pdf(pdf_path)
    if not pages:
        print("\n❌ Could not extract text from PDF. Exiting.")
        return
    
    # Chunk and index the paper
    chunks = qa_agent.chunk_text(pages, chunk_size=400, overlap=50)
    qa_agent.index_paper(chunks, paper_title=selected_paper.title)
    
    # Step 5: Interactive Q&A
    print("\n" + "="*80)
    print("STEP 5: ASK QUESTIONS ABOUT THE PAPER")
    print("="*80)
    print("\nYou can now ask questions about the paper.")
    print("The agent will provide answers with source citations.")
    print("\nType 'quit' or 'exit' to stop.\n")
    
    question_count = 0
    while True:
        question = input("\n❓ Your question: ").strip()
        
        if question.lower() in ['quit', 'exit', 'q']:
            print("\n👋 Thank you for using the Paper Q&A Agent!")
            break
        
        if not question:
            continue
        
        question_count += 1
        
        # Get answer
        result = qa_agent.answer_question(question, top_k=3)
        
        # Display answer
        print(f"\n{'='*80}")
        print("✨ ANSWER:")
        print('='*80)
        print(result['answer'])
        
        # Display sources
        print(f"\n{'='*80}")
        print("📚 SOURCES USED:")
        print('='*80)
        for source in result['sources']:
            print(f"\n[Source {source['source_id']}]")
            print(f"  📄 Page: {source['page']}")
            print(f"  📑 Section: {source['section']}")
            if source['relevance_score']:
                print(f"  🎯 Relevance: {source['relevance_score']:.2%}")
            print(f"  📝 Text Preview:")
            print(f"     {source['text_preview']}")
        
        print("\n" + "-"*80)
    
    # Summary
    print("\n" + "="*80)
    print("SESSION SUMMARY")
    print("="*80)
    print(f"Paper analyzed: {selected_paper.title}")
    print(f"Questions asked: {question_count}")
    print(f"Chunks indexed: {len(chunks)}")
    print("="*80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Exiting...")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()