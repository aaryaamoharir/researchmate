"""Answer agent — retrieval + generation with cited answers.

Calls teammate MCP tools in sequence:
  vector_search -> (google_search) -> (research_paper_search) -> Groq LLM

Does NOT implement any MCP tool logic — only orchestration and generation.
"""

from __future__ import annotations

import logging
import os

from groq import Groq

from agent_interfaces import (
    AnswerOutcome,
    Citation,
    MCPToolClient,
)

logger = logging.getLogger(__name__)


class AnswerAgent:
    """Retrieval + generation agent that produces cited answers."""

    def __init__(
        self,
        client: MCPToolClient,
        *,
        min_score: float = 0.5,
        min_good_matches: int = 2,
    ) -> None:
        self._client = client
        self._min_score = min_score
        self._min_good_matches = min_good_matches
        self._groq = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
        self._last_exc: Exception | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def answer(
        self,
        query: str,
        *,
        doc_id: str | None = None,
        filters: dict | None = None,
        top_k: int = 6,
        enable_fallback: bool = True,
        include_papers: bool = True,
    ) -> AnswerOutcome:
        """Run retrieval pipeline and generate a cited answer."""

        citations: list[Citation] = []
        sources_used: list[str] = []

        # 1. vector_search (always)
        vs_payload: dict = {"query": query, "top_k": top_k}
        if doc_id:
            vs_payload["doc_id"] = doc_id
        if filters:
            vs_payload["filters"] = filters

        vs_result = self._call_tool("vector_search", vs_payload)
        if vs_result is not None:
            sources_used.append("vector_search")
            for m in vs_result.get("matches", []):
                citations.append({
                    "source_id": f"v:{m['chunk_id']}",
                    "source_type": "vector",
                    "snippet": m.get("text", ""),
                    "score": m.get("score", 0.0),
                    "metadata": m.get("metadata", {}),
                })

        # 2. Evaluate sufficiency — count matches above threshold
        good_count = sum(
            1 for c in citations if c.get("score", 0) >= self._min_score
        )
        needs_fallback = good_count < self._min_good_matches

        # 3. google_search (conditional fallback)
        if needs_fallback and enable_fallback:
            gs_result = self._call_tool(
                "google_search", {"query": query, "max_results": top_k},
            )
            if gs_result is not None:
                sources_used.append("google_search")
                for hit in gs_result.get("results", []):
                    citations.append({
                        "source_id": hit.get("source_id", ""),
                        "source_type": "web",
                        "title": hit.get("title", ""),
                        "snippet": hit.get("snippet", ""),
                        "score": hit.get("score", 0.0),
                        "url": hit.get("url", ""),
                    })

        # 4. research_paper_search (optional, always if enabled)
        if include_papers:
            ps_result = self._call_tool(
                "research_paper_search", {"query": query},
            )
            if ps_result is not None:
                sources_used.append("research_paper_search")
                for paper in ps_result.get("papers", []):
                    citations.append({
                        "source_id": paper.get("source_id", ""),
                        "source_type": "paper",
                        "title": paper.get("title", ""),
                        "snippet": paper.get("abstract", ""),
                        "url": paper.get("url", ""),
                    })

        # 5. No context check
        if not citations:
            return {
                "status": "no_context",
                "query": query,
                "citations": [],
                "sources_used": sources_used,
            }

        # 6. LLM generation
        try:
            answer_text = self._generate(query, citations)
        except Exception as exc:
            logger.error("LLM generation failed: %s", exc)
            return {
                "status": "error",
                "query": query,
                "error": str(exc),
                "citations": citations,
                "sources_used": sources_used,
            }

        return {
            "status": "success",
            "answer": answer_text,
            "query": query,
            "citations": citations,
            "sources_used": sources_used,
        }

    def answer_loop(self) -> None:
        """Interactive REPL for the answer agent."""
        print("Ask questions about your papers (type 'quit' to exit)")
        print("-" * 40)

        while True:
            try:
                query = input("\nYou: ").strip()
                if not query:
                    continue
                if query.lower() == "quit":
                    print("Goodbye!")
                    break

                outcome = self.answer(query)
                self._print_outcome(outcome)
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as exc:
                print(f"\nError: {exc}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate(self, query: str, citations: list[Citation]) -> str:
        """Build context from citations and call Groq LLM."""

        # Group citations by source type
        groups: dict[str, list[Citation]] = {}
        for c in citations:
            stype = c.get("source_type", "unknown")
            groups.setdefault(stype, []).append(c)

        label_map = {
            "vector": "Document Chunks",
            "web": "Web Sources",
            "paper": "Academic Papers",
        }

        context_parts: list[str] = []
        for stype, group_citations in groups.items():
            label = label_map.get(stype, stype.title())
            context_parts.append(f"## {label}")
            for c in group_citations:
                sid = c.get("source_id", "?")
                snippet = c.get("snippet", "")
                title = c.get("title", "")
                header = f"[{sid}]"
                if title:
                    header += f" {title}"
                context_parts.append(f"{header}\n{snippet}")
            context_parts.append("")

        context_block = "\n\n".join(context_parts)

        system_prompt = (
            "You are a research assistant. Answer the user's question using "
            "ONLY the provided context. Cite your sources using [source_id] "
            "inline. If the context does not contain enough information, say so."
        )

        user_prompt = (
            f"Context:\n{context_block}\n\n"
            f"Question: {query}"
        )

        response = self._groq.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=1024,
        )

        return response.choices[0].message.content or ""

    def _call_tool(self, tool_name: str, payload: dict) -> dict | None:
        """Call an MCP tool. Returns the response dict, or None on failure."""
        try:
            result = self._client.call(tool_name, payload)
            self._last_exc = None
            return result
        except Exception as exc:
            self._last_exc = exc
            logger.error("%s failed: %s", tool_name, exc)
            return None

    def _print_outcome(self, outcome: AnswerOutcome) -> None:
        """Pretty-print an answer outcome to the terminal."""
        status = outcome.get("status", "unknown")

        if status == "no_context":
            print("\nNo relevant context found for your query.")
            return

        if status == "error":
            print(f"\nError: {outcome.get('error', 'unknown')}")
            return

        answer = outcome.get("answer", "")
        print(f"\nAnswer:\n{answer}")

        citations = outcome.get("citations", [])
        if citations:
            print(f"\nSources ({len(citations)}):")
            for c in citations:
                sid = c.get("source_id", "?")
                title = c.get("title", "")
                stype = c.get("source_type", "")
                line = f"  [{sid}] ({stype})"
                if title:
                    line += f" {title}"
                print(line)
