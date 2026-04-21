"""
agent.py — Agent brain for the mini-wiki backend.

This module is the central controller that:

1. **Classifies intent** — determines what the user wants via keyword rules.
2. **Routes to the right tool** — rag_pipeline, ingest_pipeline, or lint_pipeline.
3. **Scores confidence** — based on retrieval similarity scores.
4. **Logs interactions** — appends a summary entry to ``wiki/log.md``.
5. **Manages memory** — persists the exchange into the short-term store.
6. **Self-improves** — writes new synthesis pages to ``wiki/syntheses/`` and
   updates ``wiki/index.md`` when a synthesis produces meaningful new content.

Public API::

    from core.agent import run, classify_intent

    result = run("What is RAG?")
    # {
    #   "answer": "...",
    #   "intent": "search",
    #   "actions_taken": ["retrieve"],
    #   "sources": [...],
    #   "confidence": "high",
    #   "context": [...],
    # }
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from core import memory

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Minimum number of words required for a query to be attempted rather than
# triggering the ask_clarification action.  Queries with fewer words and no
# recognised intent are almost always too vague to retrieve useful results.
_MIN_QUERY_WORDS = 3

# Maximum characters kept from the user query when used as a page title or
# YAML frontmatter value, to stay within a readable heading width.
_MAX_TITLE_LENGTH = 80

# Maximum characters in a generated slug (used as part of a filename).
# Keeps filenames short and compatible with all filesystems.
_MAX_SLUG_LENGTH = 60

# Phrases that signal the LLM could not answer from context.  When the answer
# matches any of these prefixes the agent will not save a synthesis page
# (there is nothing worthwhile to persist).
_NO_ANSWER_PREFIXES = (
    "i don't know",
    "i do not know",
    "i'm not sure",
    "i am not sure",
    "i don't have",
    "i do not have",
    "not enough information",
    "insufficient context",
)

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

    answer = generator.generate(query, chunks, history=history)

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


def write_wiki_page(content: str, location: str) -> dict[str, Any]:
    """Write (or append to) a synthesis page in ``wiki/syntheses/``.

    Safety rules
    ------------
    - If the target file already exists, new content is *appended* under a
      versioned heading rather than overwriting the file.
    - The ``wiki/index.md`` Syntheses table is updated with a new row when the
      file is first created.
    - An entry is appended to ``wiki/log.md``.

    Parameters
    ----------
    content : str
        Markdown text to write to the page.
    location : str
        Filename (or relative path under ``wiki/``) for the new page.
        If it does not start with ``wiki/``, ``wiki/syntheses/`` is prepended.
        The ``.md`` extension is added automatically if absent.

    Returns
    -------
    dict
        Keys: ``answer``, ``sources``, ``context``, ``confidence``.
    """
    # Resolve target path safely inside the repo
    if not location.endswith(".md"):
        location = location + ".md"
    if not location.startswith("wiki/"):
        location = "wiki/syntheses/" + location.lstrip("/")

    target = REPO_ROOT / location
    target.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_new = not target.exists()

    try:
        if is_new:
            target.write_text(content, encoding="utf-8")
        else:
            # Append-only: add a versioned section so existing content is preserved
            versioned_section = (
                f"\n\n---\n\n## Update — {timestamp}\n\n{content}"
            )
            with target.open("a", encoding="utf-8") as fh:
                fh.write(versioned_section)
    except OSError as exc:
        return {
            "answer": f"Failed to write wiki page: {exc}",
            "sources": [],
            "context": [],
            "confidence": "low",
        }

    # Update wiki/index.md Syntheses table when creating a new page
    if is_new:
        _update_index_for_synthesis(location, content)

    # Log to wiki/log.md
    action = "created" if is_new else "appended"
    _log_wiki_update(location, action, timestamp)

    return {
        "answer": f"Synthesis page {action}: {location}",
        "sources": [location],
        "context": [content[:300]],
        "confidence": "high",
    }


def _slug_from_content(content: str) -> str:
    """Derive a short slug from the first heading or first line of *content*."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
            return slug[:_MAX_SLUG_LENGTH] or "synthesis"
    # Fallback: use the first non-empty line
    first = next((l.strip() for l in content.splitlines() if l.strip()), "synthesis")
    return re.sub(r"[^a-z0-9]+", "-", first.lower()).strip("-")[:_MAX_SLUG_LENGTH] or "synthesis"


def _is_no_answer(text: str) -> bool:
    """Return True when the LLM reply indicates it could not answer."""
    normalised = text.strip().lower()
    return any(normalised.startswith(prefix) for prefix in _NO_ANSWER_PREFIXES)


def _extract_summary(content: str, max_length: int = 100) -> str:
    """Extract the first meaningful body line from markdown *content*.

    Skips YAML frontmatter (lines between ``---`` delimiters), headings, and
    blank lines so the summary captures actual prose rather than metadata.
    """
    in_frontmatter = False
    lines = content.splitlines()
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        # Toggle frontmatter block on the opening/closing ``---``
        if stripped == "---":
            in_frontmatter = i == 0 or in_frontmatter
            in_frontmatter = not in_frontmatter if i != 0 else True
            continue
        if in_frontmatter:
            continue
        if stripped and not stripped.startswith("#"):
            return stripped[:max_length]
    return ""


def _update_index_for_synthesis(location: str, content: str) -> None:
    """Append a row to the Syntheses table in ``wiki/index.md``."""
    index_file = REPO_ROOT / "wiki" / "index.md"
    if not index_file.exists():
        return

    # Extract a one-line summary, skipping frontmatter and headings
    summary = _extract_summary(content)

    # Derive [[slug]] from filename
    stem = Path(location).stem
    new_row = f"| [[{stem}]] | {summary} |\n"

    try:
        text = index_file.read_text(encoding="utf-8")
        # Insert after the Syntheses table header row if present
        if "## Syntheses" in text:
            # Find the header separator line and append after the last row in the table
            lines = text.splitlines(keepends=True)
            insert_at = None
            in_syntheses = False
            for i, line in enumerate(lines):
                if line.strip() == "## Syntheses":
                    in_syntheses = True
                if in_syntheses and line.startswith("|") and not line.startswith("| Page"):
                    insert_at = i + 1  # keep moving to last table row
            if insert_at is not None:
                lines.insert(insert_at, new_row)
                index_file.write_text("".join(lines), encoding="utf-8")
        else:
            # Append a new Syntheses section
            with index_file.open("a", encoding="utf-8") as fh:
                fh.write(f"\n## Syntheses\n| Page | Summary |\n|------|--------|\n{new_row}")
    except OSError:
        pass  # Non-fatal


def _log_wiki_update(location: str, action: str, timestamp: str) -> None:
    """Append a wiki-update entry to ``wiki/log.md``."""
    log_file = REPO_ROOT / "wiki" / "log.md"
    entry = (
        f"\n## [{timestamp}] update_wiki | {action} synthesis page\n"
        f"- File: {location}\n"
        f"- Action: {action}\n"
    )
    try:
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    except OSError:
        pass  # Non-fatal


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
    """Run the agent for *query* using a multi-step reasoning loop.

    Steps
    -----
    1. **Understand query** — classify intent and decide the initial action.
    2. **Decide action** — map intent to one of the supported actions:
       ``retrieve``, ``synthesize``, ``ingest``, ``answer_direct``,
       ``ask_clarification``.
    3. **Execute tool** — call the appropriate internal tool.
    4. **Evaluate result** — check confidence and determine if a follow-up
       action is warranted (e.g., writing a synthesis wiki page).
    5. **Self-improve** — if the result is a synthesis with sufficient
       confidence, automatically write the insight to ``wiki/syntheses/``
       (``update_wiki`` action) and update ``wiki/index.md`` / ``wiki/log.md``.

    The internal Thought → Action → Input → Observation trace is not exposed
    to the caller; only the final structured response is returned.

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
        Keys: ``answer`` (str), ``intent`` (str),
        ``actions_taken`` (list[str]), ``sources`` (list[str]),
        ``confidence`` (str), ``context`` (list[str]).
    """
    if history is None:
        history = memory.get_history()

    actions_taken: list[str] = []

    # ------------------------------------------------------------------
    # Step 1 — Understand query / classify intent
    # ------------------------------------------------------------------
    intent = classify_intent(query)

    # ------------------------------------------------------------------
    # Step 2 — Decide action based on intent
    # ------------------------------------------------------------------

    # Short or ambiguous queries → ask for clarification instead of guessing
    words = [w for w in query.strip().split() if w]
    if len(words) < _MIN_QUERY_WORDS and intent == "unknown":
        actions_taken.append("ask_clarification")
        result: dict[str, Any] = {
            "answer": (
                "Could you provide more detail? Your query seems incomplete. "
                "Try asking a full question, for example: "
                "'What is retrieval-augmented generation?'"
            ),
            "sources": [],
            "context": [],
            "confidence": "low",
        }
        _log_interaction(query, intent, [])
        memory.add_interaction(user=query, assistant=result["answer"])
        return {
            "answer": result["answer"],
            "intent": intent,
            "actions_taken": actions_taken,
            "sources": [],
            "confidence": "low",
            "context": [],
        }

    # ------------------------------------------------------------------
    # Step 3 — Execute tool
    # ------------------------------------------------------------------

    if intent == "update":
        # Thought: user wants to rebuild the vector store
        # Action: ingest
        actions_taken.append("ingest")
        result = ingest_pipeline()

    elif intent == "meta":
        # Thought: user is asking about the system itself
        # Action: answer_direct (no retrieval needed)
        actions_taken.append("answer_direct")
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

    elif intent == "synthesize":
        # Thought: user wants a deep comparison or multi-concept synthesis
        # Action: retrieve first, then synthesize
        actions_taken.append("retrieve")
        result = rag_pipeline(query, history=history)

        # ------------------------------------------------------------------
        # Step 4 — Evaluate result
        # ------------------------------------------------------------------
        # Observation: if retrieval was successful, mark as synthesize action
        if result.get("confidence") in ("high", "medium") and result.get("answer"):
            actions_taken.append("synthesize")

            # ------------------------------------------------------------------
            # Step 5 — Self-improvement: write synthesis page to wiki/syntheses/
            # ------------------------------------------------------------------
            # Action: update_wiki
            answer_text = result["answer"]
            sources = result.get("sources", [])
            if answer_text and not _is_no_answer(answer_text):
                slug = _slug_from_content(answer_text)
                # Use microsecond precision to avoid filename collisions
                timestamp_suffix = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                page_filename = f"{slug}-{timestamp_suffix}.md"
                title = query[:_MAX_TITLE_LENGTH]
                sources_str = "\n".join(f"- [[{Path(s).stem}]]" for s in sources) if sources else "- (none)"
                page_content = (
                    f"---\ntitle: \"{title}\"\ntype: synthesis\n"
                    f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
                    f"sources: [{', '.join(Path(s).stem for s in sources)}]\n---\n\n"
                    f"# {title}\n\n"
                    f"## Synthesis\n\n{answer_text}\n\n"
                    f"## Sources\n{sources_str}\n"
                )
                write_wiki_page(page_content, page_filename)
                actions_taken.append("update_wiki")

    else:
        # search or unknown — route through the RAG pipeline
        # Thought: user wants to find information
        # Action: retrieve
        actions_taken.append("retrieve")
        result = rag_pipeline(query, history=history)

    # ------------------------------------------------------------------
    # Log interaction and persist memory
    # ------------------------------------------------------------------
    answer = result.get("answer", "")
    sources = result.get("sources", [])

    _log_interaction(query, intent, sources)
    memory.add_interaction(user=query, assistant=answer)

    return {
        "answer": answer,
        "intent": intent,
        "actions_taken": actions_taken,
        "sources": sources,
        "confidence": result.get("confidence", "low"),
        "context": result.get("context", []),
    }
