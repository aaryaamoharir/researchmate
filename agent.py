from __future__ import annotations

import os
from typing import TypedDict

from langgraph.graph import END, StateGraph

from embeddings import search
from llm_client import get_chat_model, get_groq_client


class State(TypedDict):
    query: str
    page_results: list[dict]
    context: str
    response: str


def retrieve(state: State) -> State:
    """Retrieve relevant pages from the unified vector collection."""
    page_hits = search(state["query"], top_k=10)
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
                "text": payload.get("text", ""),
                "summary": payload.get("summary", ""),
                "score": score,
            }
        )

    state["page_results"] = page_results

    context_parts = []
    for r in page_results:
        pdf_label = os.path.basename(r.get("pdf", "")) or "unknown.pdf"
        page = r.get("page", "?")
        content = r.get("summary") or r.get("text", "")
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
        "Only say you cannot answer if the context truly contains no relevant information."
    )

    user_prompt = (
        "Context from research papers:\n"
        f"{state['context']}\n\n"
        f"Question: {state['query']}\n\n"
        "Answer:"
    )

    response = client.chat.completions.create(
        model=get_chat_model(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
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


def chat(query: str) -> str:
    result = agent.invoke(
        {
            "query": query,
            "page_results": [],
            "context": "",
            "response": "",
        }
    )
    return result["response"]
