"""CLI for the hybrid research paper RAG system."""

import glob
import sys
from chunks import extract_text_chunks
from images import extract_figures
from embeddings import create_collections, store_text_chunks, store_figures
from agent import chat


def index():
    """Index all PDFs: extract text chunks and figures."""
    create_collections()
    pdf_files = glob.glob("arxiv_pdfs/*.pdf")

    if not pdf_files:
        print("No PDF files found in arxiv_pdfs/")
        return

    for pdf in pdf_files:
        print(f"\nProcessing: {pdf}")

        # Extract and store text chunks
        try:
            chunks = extract_text_chunks(pdf)
            store_text_chunks(chunks)
        except Exception as e:
            print(f"  Text extraction error: {e}")

        # Extract and store figures
        try:
            figures = extract_figures(pdf)
            store_figures(figures)
        except Exception as e:
            print(f"  Figure extraction error: {e}")

    print(f"\nIndexed {len(pdf_files)} PDFs")


def run_chat():
    """Run the interactive chat interface."""
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
        except Exception as e:
            print(f"\nError: {e}")


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "index":
            index()
        elif command == "chat":
            run_chat()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python main.py [index|chat]")
    else:
        run_chat()


if __name__ == "__main__":
    main()
