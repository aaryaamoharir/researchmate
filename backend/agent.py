"""RAG chat pipeline — retrieve relevant pages from Qdrant, answer via Groq."""

from __future__ import annotations

import os
from typing import TypedDict

from langgraph.graph import END, StateGraph

from embeddings import search
from llm_client import get_chat_model, get_groq_client


class State(TypedDict):
    query: str
    messages: list[dict]
    pdf_id: int | None
    page_results: list[dict]
    context: str
    response: str


def _build_search_query(messages: list[dict], query: str) -> str:
    """Combine recent conversation context with the latest query for better retrieval.

    If the latest query is vague (e.g. "what are the tradeoffs?"), prepending
    recent context helps the embedding model find the right pages.
    """
    recent_context = []
    # Grab last few messages (excluding the current query) for context
    for msg in messages[:-1][-4:]:
        recent_context.append(msg.get("content", ""))

    if recent_context:
        return " ".join(recent_context) + " " + query
    return query


def retrieve(state: State) -> State:
    """Retrieve relevant pages from Qdrant, optionally filtered by pdf_id."""
    search_query = _build_search_query(state.get("messages", []), state["query"])
    page_hits = search(search_query, top_k=10, pdf_id=state.get("pdf_id"))
    page_results: list[dict] = []

    for hit in page_hits:
        payload = getattr(hit, "payload", {}) or {}
        if payload.get("type") == "paper_summary":
            continue
        score = getattr(hit, "score", 0.0)
        page_results.append(
            {
                "pdf": payload.get("pdf", ""),
                "page": payload.get("page", 0),
                "summary": payload.get("summary", ""),
                "score": score,
            }
        )

    state["page_results"] = page_results

    context_parts = []
    for r in page_results:
        pdf_label = os.path.basename(r.get("pdf", "")) or "unknown.pdf"
        page = r.get("page", "?")
        content = r.get("summary", "")
        context_parts.append(f"[{pdf_label} Page {page}]: {content}")

    state["context"] = "\n\n".join(context_parts)
    return state


def generate(state: State) -> State:
    if not state["page_results"]:
        state["response"] = "No relevant content found. Please index some papers first."
        return state

    client = get_groq_client()

    system_prompt = (
        "You are a helpful research assistant. Answer questions based on the "
        "provided context from research papers. Be concise and accurate. "
        "Always cite which page the information comes from. "
        "Only say you cannot answer if the context truly contains no relevant information.\n\n"
        "Context from research papers:\n"
        f"{state['context']}"
    )

    # Build the message list: system prompt + full conversation history
    llm_messages = [{"role": "system", "content": system_prompt}]

    for msg in state.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant"):
            llm_messages.append({"role": role, "content": content})

    # If no messages were passed, fall back to just the query
    if len(llm_messages) == 1:
        llm_messages.append({"role": "user", "content": state["query"]})

    response = client.chat.completions.create(
        model=get_chat_model(),
        messages=llm_messages,
        temperature=0.3,
        max_tokens=1024,
    )

    state["response"] = response.choices[0].message.content or ""
    return state


def build_agent():
    graph = StateGraph(State)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    graph.set_entry_point("retrieve")
    return graph.compile()


agent = build_agent()


def chat(query: str, pdf_id: int | None = None, messages: list[dict] | None = None) -> str:
    """Run the RAG pipeline. If pdf_id is given, only search that paper."""
    result = agent.invoke(
        {
            "query": query,
            "messages": messages or [],
            "pdf_id": pdf_id,
            "page_results": [],
            "context": "",
            "response": "",
        }
    )
    return result["response"]
