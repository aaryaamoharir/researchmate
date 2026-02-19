"""Typed interfaces and contracts for the ingestion agent.

Defines:
- MCPToolClient: generic protocol for calling teammate MCP tools
- TypedDicts for every tool request/response shape the agent constructs or validates
- IngestionJobOptions defaults
"""

from __future__ import annotations

from typing import Protocol, TypedDict


# ---------------------------------------------------------------------------
# Generic MCP transport protocol
# ---------------------------------------------------------------------------

class MCPToolClient(Protocol):
    """Minimal interface for calling MCP tools.

    Implementations may wrap HTTP, stdio, or an in-process fake.
    The agent never depends on transport details.
    """

    def call(self, tool_name: str, payload: dict) -> dict: ...


# ---------------------------------------------------------------------------
# Queue contracts
# ---------------------------------------------------------------------------

class IngestionJobOptions(TypedDict, total=False):
    """Optional overrides carried inside a queue message payload."""
    chunk_strategy: str       # default: "section_aware"
    max_chars: int            # default: 1200
    overlap_chars: int        # default: 150
    embedding_model: str      # default: "all-MiniLM-L6-v2"
    make_summary: bool        # default: False


OPTION_DEFAULTS: dict[str, object] = {
    "chunk_strategy": "section_aware",
    "max_chars": 1200,
    "overlap_chars": 150,
    "embedding_model": "all-MiniLM-L6-v2",
    "make_summary": False,
}


class IngestionJobPayload(TypedDict):
    """The payload inside a queue message."""
    job_type: str              # e.g. "INGEST_PDF"
    doc_id: str
    user_id: str
    storage_url: str
    created_at: str            # ISO-8601
    options: IngestionJobOptions


class QueueMessage(TypedDict):
    """A single message returned by queue_pop."""
    job_id: str
    receipt: str
    payload: IngestionJobPayload


class QueuePopResponse(TypedDict):
    """Response from queue_pop."""
    messages: list[QueueMessage]


class QueueAckError(TypedDict):
    """Error detail sent with a FAILED ack."""
    code: str
    message: str
    retryable: bool


class QueueAckResult(TypedDict, total=False):
    """Success detail sent with a SUCCESS ack."""
    doc_id: str
    chunk_count: int


# ---------------------------------------------------------------------------
# pdf_extract_text contracts
# ---------------------------------------------------------------------------

class PdfPage(TypedDict):
    """A single page of extracted text."""
    page: int                  # 1-indexed
    text: str


class PdfExtractMeta(TypedDict, total=False):
    """Optional metadata from pdf_extract_text."""
    num_pages: int
    extraction_method: str
    language: str


class PdfExtractResult(TypedDict):
    """Response from pdf_extract_text."""
    doc_id: str
    pages: list[PdfPage]
    meta: PdfExtractMeta


# ---------------------------------------------------------------------------
# chunk_document contracts
# ---------------------------------------------------------------------------

class ChunkConfig(TypedDict, total=False):
    """Configuration for the chunking tool."""
    strategy: str
    max_chars: int
    overlap_chars: int


class Chunk(TypedDict):
    """A single chunk returned by chunk_document."""
    chunk_id: str
    text: str
    page_start: int
    page_end: int
    offset_start: int         # offset within page text
    offset_end: int           # offset within page text
    section_title: str | None


class ChunkDocumentMeta(TypedDict, total=False):
    """Optional metadata from chunk_document."""
    chunk_count: int


class ChunkDocumentResult(TypedDict):
    """Response from chunk_document."""
    doc_id: str
    chunks: list[Chunk]
    meta: ChunkDocumentMeta


# ---------------------------------------------------------------------------
# embed_texts contracts
# ---------------------------------------------------------------------------

class EmbedInput(TypedDict):
    """A single text input for embedding."""
    id: str
    text: str


class EmbedOutput(TypedDict):
    """A single embedding result."""
    id: str
    vector: list[float]


class EmbedTextsResult(TypedDict):
    """Response from embed_texts."""
    model: str
    dim: int
    embeddings: list[EmbedOutput]


# ---------------------------------------------------------------------------
# vector_upsert contracts
# ---------------------------------------------------------------------------

class VectorMetadata(TypedDict, total=False):
    """Metadata attached to each vector."""
    doc_id: str
    chunk_id: str
    page_start: int
    page_end: int
    section_title: str | None


class VectorRecord(TypedDict):
    """A single vector to upsert."""
    id: str
    vector: list[float]
    metadata: VectorMetadata


class VectorUpsertResult(TypedDict):
    """Response from vector_upsert."""
    upserted: int


# ---------------------------------------------------------------------------
# Agent outcome (returned by run_once)
# ---------------------------------------------------------------------------

class IngestionOutcome(TypedDict, total=False):
    """Structured result from a single ingestion run."""
    status: str          # "idle" | "success" | "failed" | "fatal"
    doc_id: str | None
    chunk_count: int
    error: QueueAckError


# ---------------------------------------------------------------------------
# vector_search contracts (answer agent)
# ---------------------------------------------------------------------------

class VectorSearchFilters(TypedDict, total=False):
    """Optional filters for vector_search."""
    section_title: str


class VectorMatch(TypedDict):
    """A single match returned by vector_search."""
    chunk_id: str
    score: float
    text: str
    metadata: dict


class VectorSearchResult(TypedDict):
    """Response from vector_search."""
    matches: list[VectorMatch]


# ---------------------------------------------------------------------------
# google_search contracts (answer agent)
# ---------------------------------------------------------------------------

class GoogleSearchHit(TypedDict):
    """A single hit from google_search."""
    source_id: str
    title: str
    snippet: str
    url: str
    score: float


class GoogleSearchResult(TypedDict):
    """Response from google_search."""
    results: list[GoogleSearchHit]


# ---------------------------------------------------------------------------
# research_paper_search contracts (answer agent)
# ---------------------------------------------------------------------------

class PaperHit(TypedDict, total=False):
    """A single paper from research_paper_search."""
    source_id: str
    title: str
    authors: list[str]
    year: int
    abstract: str
    url: str
    doi: str


class PaperSearchResult(TypedDict):
    """Response from research_paper_search."""
    papers: list[PaperHit]


# ---------------------------------------------------------------------------
# Answer agent outcome
# ---------------------------------------------------------------------------

class Citation(TypedDict, total=False):
    """A single citation used in the answer."""
    source_id: str
    source_type: str       # "vector" | "web" | "paper"
    title: str
    snippet: str
    score: float
    url: str
    metadata: dict


class AnswerOutcome(TypedDict, total=False):
    """Structured result from the answer agent."""
    status: str            # "success" | "no_context" | "error"
    answer: str
    citations: list[Citation]
    sources_used: list[str]
    query: str
    error: str
