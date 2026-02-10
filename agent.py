"""LangGraph chat agent with hybrid retrieval and Groq LLM."""

import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

# Load .env file
load_dotenv()
from typing import TypedDict
from groq import Groq
from embeddings import search_all

# Initialize Groq client
groq_client = None


def get_groq_client():
    global groq_client
    if groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")
        groq_client = Groq(api_key=api_key)
    return groq_client


class State(TypedDict):
    query: str
    text_results: list[dict]
    figure_results: list[dict]
    context: str
    response: str


def retrieve(state: State) -> State: #retreive func for text/figs from paper
    results = search_all(state["query"], top_k=5)

    state["text_results"] = [
        {
            "pdf": r.payload["pdf"],
            "page": r.payload["page"],
            "text": r.payload.get("text", ""),
            "score": r.score
        }
        for r in results["text"]
    ]

    state["figure_results"] = [
        {
            "pdf": r.payload["pdf"],
            "page": r.payload["page"],
            "score": r.score
        }
        for r in results["figures"]
    ]

    # Build context from retrieved text
    context_parts = []
    for r in state["text_results"]:
        context_parts.append(f"[Page {r['page']}]: {r['text']}")

    state["context"] = "\n\n".join(context_parts)
    return state


def generate(state: State) -> State: #groq to make response
    if not state["text_results"] and not state["figure_results"]:
        state["response"] = "No relevant content found. Please index some papers first."
        return state

    client = get_groq_client()

    # Build prompt
    system_prompt = """You are a helpful research assistant. Answer questions based on the provided context from research papers.
Be concise and accurate. If the context doesn't contain enough information to answer, say so.
Always cite the page numbers when referencing specific information."""

    user_prompt = f"""Context from research papers:
{state['context']}

Question: {state['query']}

Answer:"""

    # Call Groq
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=1024
    )

    answer = response.choices[0].message.content

    # Add figure references if any
    if state["figure_results"]:
        figure_refs = "\n\nRelated figures found on: " + ", ".join(
            f"Page {r['page']}" for r in state["figure_results"]
        )
        answer += figure_refs

    state["response"] = answer
    return state


def build_agent():
    """Build and compile the LangGraph agent."""
    graph = StateGraph(State)

    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)

    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    graph.set_entry_point("retrieve")

    return graph.compile()


# Compile agent
agent = build_agent()


def chat(query: str) -> str:
    """Run a chat query through the agent."""
    result = agent.invoke({
        "query": query,
        "text_results": [],
        "figure_results": [],
        "context": "",
        "response": ""
    })
    return result["response"]
