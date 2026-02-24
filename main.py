"""CLI for the hybrid research paper RAG system."""

from __future__ import annotations

import argparse
import glob
import logging

from agent_interfaces import MCPToolClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stub MCP client (replaced when teammates deliver real MCP tools)
# ---------------------------------------------------------------------------

class StubMCPToolClient:
    """Placeholder MCP client - raises on every call.

    Lives here (CLI wiring concern) so agents stay transport-agnostic.
    Swap this for the real client once MCP tools are connected; only
    main.py needs to change.
    """

    def call(self, tool_name: str, payload: dict) -> dict:
        raise NotImplementedError(
            f"StubMCPToolClient: tool '{tool_name}' is not connected yet. "
            "Replace StubMCPToolClient with a real MCPToolClient implementation."
        )


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_index(args: argparse.Namespace) -> None:
    """Index all PDFs as page-level ColQwen2 embeddings."""
    from embeddings import create_collection, index_pdf

    create_collection(recreate=args.recreate, drop_legacy=not args.keep_legacy)
    pdf_files = glob.glob("arxiv_pdfs/*.pdf")

    if not pdf_files:
        print("No PDF files found in arxiv_pdfs/")
        return

    total_pages_indexed = 0
    for pdf in pdf_files:
        print(f"\nProcessing: {pdf}")
        try:
            result = index_pdf(pdf, batch_size=args.batch_size, dpi_scale=args.dpi_scale)
            total_pages_indexed += int(result.get("pages_indexed", 0))
        except Exception as exc:
            print(f"  Indexing error: {exc}")

    print(f"\nIndexed {len(pdf_files)} PDFs ({total_pages_indexed} pages)")


def cmd_chat(args: argparse.Namespace) -> None:
    """Run the interactive LangGraph chat interface."""
    from agent import chat

    print("Chat with your papers (type 'quit' to exit)")
    print("-" * 40)

    while True:
        try:
            query = input("\nYou: ").strip()
            if not query:
                continue
            if query.lower() == "quit":
                print("Goodbye!")
                break

            response = chat(query)
            print(f"\nBot:\n{response}")
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as exc:
            print(f"\nError: {exc}")


def cmd_ingest_once(args: argparse.Namespace) -> None:
    """Run the ingestion agent for a single job."""
    from ingestion_agent import IngestionAgent

    client: MCPToolClient = StubMCPToolClient()
    agent = IngestionAgent(client)
    outcome = agent.run_once()
    logger.info("Ingestion outcome: %s", outcome)
    print(f"Outcome: {outcome}")


def cmd_ingest_worker(args: argparse.Namespace) -> None:
    """Run the ingestion agent as a polling worker."""
    from ingestion_agent import IngestionAgent

    client: MCPToolClient = StubMCPToolClient()
    agent = IngestionAgent(client)
    agent.run_loop(poll_interval_s=args.poll_interval)


def cmd_ask(args: argparse.Namespace) -> None:
    """Run a single-shot answer query."""
    from answer_agent import AnswerAgent

    client: MCPToolClient = StubMCPToolClient()
    agent = AnswerAgent(client)

    filters = {}
    if args.section:
        filters["section_title"] = args.section

    outcome = agent.answer(
        args.query,
        doc_id=args.doc_id,
        filters=filters or None,
        top_k=args.top_k,
        enable_fallback=not args.no_fallback,
        include_papers=not args.no_papers,
    )
    agent._print_outcome(outcome)


def cmd_ask_loop(args: argparse.Namespace) -> None:
    """Run the interactive answer agent REPL."""
    from answer_agent import AnswerAgent

    client: MCPToolClient = StubMCPToolClient()
    agent = AnswerAgent(client)
    agent.answer_loop()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="researchmate",
        description="Hybrid research paper RAG system",
    )
    subs = parser.add_subparsers(dest="command")

    # index
    index_p = subs.add_parser("index", help="Index PDFs from arxiv_pdfs/")
    index_p.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the unified collection before indexing",
    )
    index_p.add_argument(
        "--keep-legacy",
        action="store_true",
        help="Do not delete legacy papers_text / papers_visual collections",
    )
    index_p.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Embedding batch size for page images (default: 8)",
    )
    index_p.add_argument(
        "--dpi-scale",
        type=float,
        default=2.0,
        help="Page render scale factor (default: 2.0)",
    )

    # chat
    subs.add_parser("chat", help="Interactive LangGraph chat REPL")

    # ingest-once
    subs.add_parser("ingest-once", help="Run ingestion agent for one job")

    # ingest-worker
    iw = subs.add_parser("ingest-worker", help="Run ingestion agent as polling worker")
    iw.add_argument(
        "--poll-interval",
        type=int,
        default=2,
        help="Seconds between queue polls (default: 2)",
    )

    # ask
    ask_p = subs.add_parser("ask", help="Single-shot answer query")
    ask_p.add_argument("query", help="The question to answer")
    ask_p.add_argument("--doc-id", default=None, help="Restrict search to a document")
    ask_p.add_argument("--section", default=None, help="Filter by section title")
    ask_p.add_argument("--top-k", type=int, default=6, help="Number of results (default: 6)")
    ask_p.add_argument("--no-fallback", action="store_true", help="Disable web search fallback")
    ask_p.add_argument("--no-papers", action="store_true", help="Disable academic paper search")

    # ask-loop
    subs.add_parser("ask-loop", help="Interactive answer agent REPL")

    return parser


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

DISPATCH = {
    "index": cmd_index,
    "chat": cmd_chat,
    "ingest-once": cmd_ingest_once,
    "ingest-worker": cmd_ingest_worker,
    "ask": cmd_ask,
    "ask-loop": cmd_ask_loop,
}


def main() -> None:
    """Main entry point."""
    logging.basicConfig(level=logging.INFO)

    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    handler = DISPATCH[args.command]
    handler(args)


if __name__ == "__main__":
    main()
