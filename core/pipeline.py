"""
pipeline.py — End-to-end RAG pipeline for mini-wiki.

Combines the retriever and generator into a single ``ask`` function that:
1. Retrieves semantically relevant chunks from the FAISS vector store.
2. Passes those chunks to the LLM generator together with the user query.
3. Returns a structured result dict ready to be serialised as JSON.
"""

from __future__ import annotations

import re
from typing import Any

from core import generator, retriever
from core._settings import get_settings

# Regex that matches the opening line of a contradiction warning block so we
# can identify and extract the block from retrieved page content.
_CONTRADICTION_BLOCK_RE = re.compile(
    r"---\s*\n⚠️ CONTRADICTION DETECTED\n(.*?)---",
    re.DOTALL,
)


def extract_contradiction_warnings(chunks: list[str]) -> list[str]:
    """Scan *chunks* for embedded ⚠️ CONTRADICTION DETECTED blocks.

    When the ingestion pipeline detects a contradiction it prepends a warning
    block to the affected wiki page.  Those pages are later chunked and
    indexed, so the warning text may appear in retrieval results.  This
    function extracts each such block and returns it as a formatted warning
    string so callers can surface it to the user.

    Parameters
    ----------
    chunks : list[str]
        Raw text chunks returned by the retriever.

    Returns
    -------
    list[str]
        De-duplicated list of human-readable warning strings extracted from
        the chunks.  Empty when no warnings are found.
    """
    seen: set[str] = set()
    warnings: list[str] = []
    for chunk in chunks:
        for match in _CONTRADICTION_BLOCK_RE.finditer(chunk):
            block_body = match.group(1).strip()
            if block_body not in seen:
                seen.add(block_body)
                warnings.append("⚠️ CONTRADICTION DETECTED\n" + block_body)
    return warnings


# Keep the private name as a backwards-compatible alias.
_extract_contradiction_warnings = extract_contradiction_warnings


def ask(query: str) -> dict[str, Any]:
    """Run the full RAG pipeline for *query*.

    Parameters
    ----------
    query : str
        The user's natural-language question.

    Returns
    -------
    dict with keys:
        ``answer``         – LLM-generated answer (grounded in context).
        ``sources``        – de-duplicated list of source file names.
        ``context``        – list of raw text chunks used as context.
        ``contradictions`` – list of contradiction warning strings extracted
                             from the retrieved pages (empty when none found).
    """
    settings = get_settings()
    top_k: int = int(settings["retrieval"]["top_k"])

    # 1. Retrieve relevant chunks
    hits = retriever.retrieve(query, top_k=top_k)

    chunks: list[str] = [h["text"] for h in hits]
    sources: list[str] = list(
        dict.fromkeys(h["source"] for h in hits)  # preserve order, deduplicate
    )

    # 2. Extract any contradiction warnings embedded in the retrieved pages
    contradictions: list[str] = extract_contradiction_warnings(chunks)

    # 3. Generate grounded answer
    answer: str = generator.generate(query, chunks)

    return {
        "answer": answer,
        "sources": sources,
        "context": chunks,
        "contradictions": contradictions,
    }
