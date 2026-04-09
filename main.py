"""CLI for the research paper RAG system."""

from __future__ import annotations

import argparse
import glob
import logging

logger = logging.getLogger(__name__)


def cmd_index(args: argparse.Namespace) -> None:
    """Index all PDFs as page-level ColQwen2 embeddings with summaries."""
    from embeddings import create_collection, index_pdf

    create_collection(recreate=args.recreate)
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
    """Run the interactive chat interface."""
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="researchmate",
        description="Research paper RAG system",
    )
    subs = parser.add_subparsers(dest="command")

    index_p = subs.add_parser("index", help="Index PDFs from arxiv_pdfs/")
    index_p.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the collection before indexing",
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

    subs.add_parser("chat", help="Interactive chat REPL")

    return parser


DISPATCH = {
    "index": cmd_index,
    "chat": cmd_chat,
}


def main() -> None:
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
