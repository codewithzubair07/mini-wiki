"""
pipeline.py — End-to-end RAG pipeline for mini-wiki.

Combines the retriever and generator into a single ``ask`` function that:
1. Retrieves semantically relevant chunks from the FAISS vector store.
2. Passes those chunks to the LLM generator together with the user query.
3. Returns a structured result dict ready to be serialised as JSON.
"""

from __future__ import annotations

from typing import Any

from core import generator, retriever
from core._settings import get_settings


def ask(query: str) -> dict[str, Any]:
    """Run the full RAG pipeline for *query*.

    Parameters
    ----------
    query : str
        The user's natural-language question.

    Returns
    -------
    dict with keys:
        ``answer``   – LLM-generated answer (grounded in context).
        ``sources``  – de-duplicated list of source file names.
        ``context``  – list of raw text chunks used as context.
    """
    settings = get_settings()
    top_k: int = int(settings["retrieval"]["top_k"])

    # 1. Retrieve relevant chunks
    hits = retriever.retrieve(query, top_k=top_k)

    chunks: list[str] = [h["text"] for h in hits]
    sources: list[str] = list(
        dict.fromkeys(h["source"] for h in hits)  # preserve order, deduplicate
    )

    # 2. Generate grounded answer
    answer: str = generator.generate(query, chunks)

    return {
        "answer": answer,
        "sources": sources,
        "context": chunks,
    }
