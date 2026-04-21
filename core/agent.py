"""
agent.py — Agent brain for the mini-wiki backend.

This module is the central controller that:

1. **Classifies intent** — determines what the user wants via keyword rules.
2. **Routes to the right tool** — rag_pipeline, ingest_pipeline, or lint_pipeline.
3. **Scores confidence** — based on retrieval similarity scores.
4. **Logs interactions** — appends a summary entry to ``wiki/log.md``.
5. **Manages memory** — persists the exchange into the short-term store.

Public API::

    from core.agent import run, classify_intent

    result = run("What is RAG?")
    # {
    #   "answer": "...",
    #   "intent": "search",
    #   "sources": [...],
    #   "confidence": "high",
    #   "context": [...],
    # }
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from core import memory

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

# Keywords that strongly suggest each intent class.
_UPDATE_KEYWORDS = frozenset(
    {"ingest", "update", "rebuild", "refresh", "reindex", "vectorize", "embed"}
)
_META_KEYWORDS = frozenset(
    {"system", "health", "status", "version", "config", "settings", "help", "about", "model", "info"}
)
_SYNTHESIZE_KEYWORDS = frozenset(
    {
        "compare", "contrast", "synthesize", "combine", "summarize",
        "relationship", "difference", "similarities", "overview", "analysis",
        "analyse", "analyze", "relate", "connection", "versus", "vs",
    }
)


def classify_intent(query: str) -> str:
    """Classify the user's *query* into one of five intent classes.

    Intent classes
    --------------
    ``search``
        Standard RAG retrieval — the default for question-like queries.
    ``synthesize``
        Deep multi-concept analysis or comparison.
    ``update``
        Trigger an ingest / wiki rebuild.
    ``meta``
        System or configuration questions.
    ``unknown``
        Catch-all fallback when no intent is detected.

    The classifier uses a lightweight keyword-matching heuristic so that it
    works fully offline without any LLM call.

    Parameters
    ----------
    query : str
        The raw user query.

    Returns
    -------
    str
        One of ``"search"``, ``"synthesize"``, ``"update"``, ``"meta"``,
        or ``"unknown"``.
    """
    q_lower = query.lower()
    words = set(q_lower.split())

    # Update intent takes highest priority (explicit action keyword present)
    if _UPDATE_KEYWORDS & words:
        return "update"

    # Meta intent (system info questions)
    if _META_KEYWORDS & words:
        return "meta"

    # Synthesize intent (comparison / analysis words present)
    if _SYNTHESIZE_KEYWORDS & words:
        return "synthesize"

    # Search intent — any question-like word present
    _QUESTION_WORDS = frozenset(
        {"what", "how", "explain", "describe", "tell", "who", "where",
         "when", "why", "is", "are", "does", "do", "list", "show", "find"}
    )
    if _QUESTION_WORDS & words:
        return "search"

    # Final fallback
    return "unknown"


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def _score_confidence(hits: list[dict[str, Any]]) -> str:
    """Map retrieval scores to a human-readable confidence tier.

    Parameters
    ----------
    hits : list[dict]
        Retrieval hits, each expected to have a ``score`` key (inner-product
        similarity; higher is better after L2 normalisation).

    Returns
    -------
    str
        ``"high"`` (≥ 0.75), ``"medium"`` (≥ 0.50), or ``"low"`` otherwise.
    """
    if not hits:
        return "low"
    top_score = float(hits[0].get("score", 0.0))
    if top_score >= 0.75:
        return "high"
    if top_score >= 0.50:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Internal tools
# ---------------------------------------------------------------------------

def rag_pipeline(query: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Retrieve relevant chunks and generate a grounded answer.

    Parameters
    ----------
    query : str
        The user's natural-language question.
    history : list[dict[str, str]] | None
        Prior conversation turns (``[{"user": ..., "assistant": ...}, ...]``).
        When provided the history is included in the generator prompt.

    Returns
    -------
    dict
        Keys: ``answer``, ``sources``, ``context``, ``confidence``.
    """
    from core import generator, retriever
    from core._settings import get_settings

    settings = get_settings()
    top_k = int(settings["retrieval"]["top_k"])

    hits = retriever.retrieve(query, top_k=top_k)
    chunks: list[str] = [h["text"] for h in hits]
    sources: list[str] = list(dict.fromkeys(h["source"] for h in hits))
    confidence = _score_confidence(hits)

    answer = generator.generate(query, chunks, history=history or [])

    return {
        "answer": answer,
        "sources": sources,
        "context": chunks,
        "confidence": confidence,
    }


def ingest_pipeline() -> dict[str, Any]:
    """Run ``tools/ingest.py --embed`` to rebuild the FAISS vector store.

    Returns
    -------
    dict
        Keys: ``answer``, ``sources``, ``context``, ``confidence``.
    """
    ingest_script = REPO_ROOT / "tools" / "ingest.py"

    result = subprocess.run(
        [sys.executable, str(ingest_script), "--embed"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    if result.returncode != 0:
        return {
            "answer": f"Ingest failed: {result.stderr or result.stdout}",
            "sources": [],
            "context": [],
            "confidence": "low",
        }

    # Invalidate retrieval cache so the next query loads the fresh index
    try:
        from core import retriever
        retriever.invalidate_cache()
    except Exception:
        pass

    return {
        "answer": result.stdout.strip() or "Vector store rebuilt successfully.",
        "sources": [],
        "context": [],
        "confidence": "high",
    }


def lint_pipeline() -> dict[str, Any]:
    """Run ``tools/lint.py`` to check the wiki for broken links / issues.

    Returns
    -------
    dict
        Keys: ``answer``, ``sources``, ``context``, ``confidence``.
    """
    lint_script = REPO_ROOT / "tools" / "lint.py"

    if not lint_script.exists():
        return {
            "answer": "Lint tool not found at tools/lint.py.",
            "sources": [],
            "context": [],
            "confidence": "low",
        }

    result = subprocess.run(
        [sys.executable, str(lint_script)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    output = result.stdout.strip() or result.stderr.strip() or "Lint completed with no output."
    confidence = "high" if result.returncode == 0 else "medium"

    return {
        "answer": output,
        "sources": [],
        "context": [],
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Interaction logging
# ---------------------------------------------------------------------------

def _log_interaction(query: str, intent: str, sources: list[str]) -> None:
    """Append a brief interaction record to ``wiki/log.md``.

    Parameters
    ----------
    query : str
        The user's query.
    intent : str
        The classified intent.
    sources : list[str]
        Source files returned by the pipeline (may be empty).
    """
    log_file = REPO_ROOT / "wiki" / "log.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sources_text = ", ".join(sources) if sources else "none"

    entry = (
        f"\n## [{timestamp}] query | intent={intent}\n"
        f"- Query: {query}\n"
        f"- Sources: {sources_text}\n"
    )

    try:
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    except OSError:
        pass  # Non-fatal — logging failure must never break a query


# ---------------------------------------------------------------------------
# Agent controller
# ---------------------------------------------------------------------------

def run(query: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Run the agent for *query*.

    Steps
    -----
    1. Classify intent.
    2. Select and execute the appropriate tool.
    3. Log the interaction to ``wiki/log.md``.
    4. Store the exchange in short-term memory.
    5. Return a structured response dict.

    Parameters
    ----------
    query : str
        The user's natural-language question or command.
    history : list[dict[str, str]] | None
        Explicit conversation history.  When ``None`` the current module-level
        memory is used automatically.

    Returns
    -------
    dict
        Keys: ``answer`` (str), ``intent`` (str), ``sources`` (list[str]),
        ``confidence`` (str), ``context`` (list[str]).
    """
    if history is None:
        history = memory.get_history()

    intent = classify_intent(query)

    # --- Route to the right tool ---
    if intent == "update":
        result = ingest_pipeline()
    elif intent == "meta":
        result = {
            "answer": (
                "mini-wiki AI Assistant — local-first RAG backend. "
                "POST /ask to query the wiki, POST /ingest to rebuild the vector store, "
                "GET /health to check service status. "
                "The system uses FAISS for semantic retrieval and supports "
                "OpenAI or Ollama as LLM backends."
            ),
            "sources": [],
            "context": [],
            "confidence": "high",
        }
    else:
        # search, synthesize, unknown — all route through the RAG pipeline
        result = rag_pipeline(query, history=history)

    answer = result.get("answer", "")
    sources = result.get("sources", [])

    # Log to wiki/log.md
    _log_interaction(query, intent, sources)

    # Persist to short-term memory
    memory.add_interaction(user=query, assistant=answer)

    return {
        "answer": answer,
        "intent": intent,
        "sources": sources,
        "confidence": result.get("confidence", "low"),
        "context": result.get("context", []),
    }
