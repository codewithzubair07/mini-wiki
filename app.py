"""
app.py — FastAPI server for mini-wiki RAG backend.

Endpoints
---------
GET  /              — serve the single-page web dashboard
GET  /health        — liveness / status check
POST /ingest        — build (or rebuild) the FAISS vector store from wiki/ markdown
POST /ingest/file   — ingest an uploaded .md / .txt / .pdf file
POST /ask           — accept a natural-language query and return a grounded answer
POST /research      — fetch live web sources via PinchTab and ingest them
GET  /contradictions — return all parsed contradiction entries from wiki/contradictions.md

Start the server
----------------
    uvicorn app:app --reload --host 0.0.0.0 --port 8000

Configuration
-------------
All tuneable settings live in ``config/settings.yml``.
LLM credentials are read from environment variables:
  - ``OPENAI_API_KEY``  (when llm.provider = "openai")
  - No key needed for local Ollama usage (llm.provider = "ollama").
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="mini-wiki AI Assistant",
    description="Local-first AI assistant backed by your personal wiki — with agent-based intent routing.",
    version="2.0.0",
)

REPO_ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    """Input payload for POST /ask."""

    query: str


class AskResponse(BaseModel):
    """Structured JSON response from POST /ask."""

    answer: str
    intent: str
    actions_taken: list[str]
    sources: list[str]
    confidence: str
    context: list[str]
    contradictions: list[str] = []
    web_sources_ingested: int = 0


class IngestResponse(BaseModel):
    """Response from POST /ingest."""

    status: str
    message: str


class HealthResponse(BaseModel):
    """Response from GET /health."""

    status: str
    vectorstore_ready: bool


class ResearchRequest(BaseModel):
    """Input payload for POST /research."""

    query: str
    max_sources: int = 3


class ResearchResponse(BaseModel):
    """Response from POST /research."""

    query: str
    sources_ingested: int
    files_created: list[str]
    contradictions_found: int


class ContradictionEntry(BaseModel):
    """A single parsed contradiction entry from wiki/contradictions.md."""

    page: str
    claim_a: str
    claim_b: str
    sources: str
    detected: str


class ContradictionsResponse(BaseModel):
    """Response from GET /contradictions."""

    contradictions: list[ContradictionEntry]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, summary="Health check")
def health() -> HealthResponse:
    """Return the service status and whether the vector store is ready."""
    from core._settings import get_settings

    settings = get_settings()
    vs_dir = REPO_ROOT / settings["retrieval"]["vectorstore_dir"]
    vectorstore_ready = (vs_dir / "index.faiss").exists() and (vs_dir / "metadata.json").exists()

    return HealthResponse(
        status="ok",
        vectorstore_ready=vectorstore_ready,
    )


@app.post("/ingest", response_model=IngestResponse, summary="Build RAG vector store")
def ingest() -> IngestResponse:
    """Trigger the embedding pipeline.

    Reads every ``*.md`` file under ``wiki/``, chunks the text, generates
    embeddings, and persists a FAISS index to ``vectorstore/``.

    After a successful ingest, the retrieval cache is invalidated so the next
    ``/ask`` call will load the freshly-built index.
    """
    ingest_script = REPO_ROOT / "tools" / "ingest.py"

    result = subprocess.run(
        [sys.executable, str(ingest_script), "--embed"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Ingest failed:\n{result.stderr or result.stdout}",
        )

    # Invalidate the in-memory retrieval cache so fresh vectors are loaded
    try:
        from core import retriever
        retriever.invalidate_cache()
    except Exception:
        pass  # Non-fatal: cache will be reloaded on the next /ask call

    return IngestResponse(
        status="ok",
        message=result.stdout.strip() or "Vector store rebuilt successfully.",
    )


@app.post("/ask", response_model=AskResponse, summary="Ask a question")
def ask(request: AskRequest) -> AskResponse:
    """Accept a natural-language query and return a grounded, agent-routed answer.

    The agent:

    1. Classifies the intent (``search``, ``synthesize``, ``update``, ``meta``,
       or ``unknown``).
    2. Selects the appropriate tool (RAG pipeline, ingest pipeline, or meta
       response).
    3. Generates a grounded answer using the retrieved context and the last
       five conversation turns from short-term memory.
    4. Logs the interaction to ``wiki/log.md``.

    Returns a JSON object with the answer, classified intent, source file
    names, confidence tier, and raw context chunks.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty.")

    try:
        from core.agent import run as agent_run

        result = agent_run(request.query)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc) + " Call POST /ingest to build the vector store first.",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return AskResponse(
        answer=result["answer"],
        intent=result["intent"],
        actions_taken=result.get("actions_taken", []),
        sources=result["sources"],
        confidence=result["confidence"],
        context=result["context"],
        contradictions=result.get("contradictions", []),
        web_sources_ingested=result.get("web_sources_ingested", 0),
    )


@app.post("/research", response_model=ResearchResponse, summary="Live web research")
def research(request: ResearchRequest) -> ResearchResponse:
    """Fetch live web sources for *query* and ingest them into the wiki.

    Uses PinchTab browser automation to search DuckDuckGo, retrieve page text,
    save each source under ``raw/sources/web/``, and run the existing ingest
    pipeline on every file.

    Request body
    ------------
    ``query``
        The research topic or question.
    ``max_sources``
        Maximum number of web sources to ingest (default ``3``).

    Returns
    -------
    JSON object with ``query``, ``sources_ingested``, ``files_created``, and
    ``contradictions_found``.

    Raises
    ------
    HTTP 503
        When PinchTab is not reachable (connection refused or timeout).
    """
    from core._settings import get_settings

    settings = get_settings()
    browser_cfg = settings.get("browser", {})

    if not browser_cfg.get("enabled", True):
        raise HTTPException(
            status_code=503,
            detail=(
                "Browser service is disabled in config/settings.yml. "
                "Set browser.enabled to true to use web research."
            ),
        )

    try:
        from tools.web_ingest import web_ingest

        summary = web_ingest(request.query, max_sources=request.max_sources)
    except Exception as exc:
        # Detect connection-level errors that indicate PinchTab is not running.
        import requests as _requests

        err_str = str(exc)
        if isinstance(exc, (_requests.ConnectionError, _requests.Timeout)) or (
            "connection" in err_str.lower()
            or "refused" in err_str.lower()
            or "timeout" in err_str.lower()
        ):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Browser service unavailable. "
                    "Make sure PinchTab is running on port 9867."
                ),
            ) from exc
        raise HTTPException(status_code=500, detail=err_str) from exc

    return ResearchResponse(
        query=summary["query"],
        sources_ingested=summary["sources_ingested"],
        files_created=summary["files_created"],
        contradictions_found=summary["contradictions_found"],
    )


@app.get("/contradictions", response_model=ContradictionsResponse, summary="List detected contradictions")
def get_contradictions() -> ContradictionsResponse:
    """Parse ``wiki/contradictions.md`` and return all contradiction entries.

    Each entry in the file is expected to be a Markdown section starting with
    ``## <timestamp> — <page>``, followed by ``Claim A:``, ``Claim B:``,
    ``Sources:``, and a ``---`` separator.

    Returns
    -------
    JSON object with a ``contradictions`` list.  Returns an empty list when the
    file does not exist or contains no parseable entries.
    """
    contradictions_file = REPO_ROOT / "wiki" / "contradictions.md"

    if not contradictions_file.exists():
        return ContradictionsResponse(contradictions=[])

    text = contradictions_file.read_text(encoding="utf-8")
    entries: list[ContradictionEntry] = []

    # Each section starts with "## <timestamp> — <page>"
    section_pattern = re.compile(
        r"^## (?P<detected>[^\n]+?) — (?P<page>[^\n]+)\n"
        r"(?:.*?Claim A:\s*(?P<claim_a>[^\n]+)\n)?"
        r"(?:.*?Claim B:\s*(?P<claim_b>[^\n]+)\n)?"
        r"(?:.*?Sources:\s*(?P<sources>[^\n]+))?",
        re.MULTILINE | re.DOTALL,
    )

    for block in re.split(r"\n---\n", text):
        block = block.strip()
        if not block:
            continue
        m = section_pattern.search(block)
        if not m:
            continue
        entries.append(
            ContradictionEntry(
                page=m.group("page").strip() if m.group("page") else "",
                claim_a=m.group("claim_a").strip() if m.group("claim_a") else "",
                claim_b=m.group("claim_b").strip() if m.group("claim_b") else "",
                sources=m.group("sources").strip() if m.group("sources") else "",
                detected=m.group("detected").strip() if m.group("detected") else "",
            )
        )

    return ContradictionsResponse(contradictions=entries)


@app.post("/ingest/file", response_model=IngestResponse, summary="Ingest an uploaded file")
async def ingest_file(file: UploadFile = File(...)) -> IngestResponse:
    """Accept an uploaded ``.md``, ``.txt``, or ``.pdf`` file, save it under
    ``raw/sources/``, and rebuild the vector store.

    Parameters
    ----------
    file
        The multipart file upload.  Only ``.md``, ``.txt``, and ``.pdf``
        extensions are accepted.

    Returns
    -------
    IngestResponse with status and a brief result message.

    Raises
    ------
    HTTP 400
        When the uploaded file type is not supported.
    HTTP 500
        When the ingest pipeline exits with a non-zero return code.
    """
    allowed = {".md", ".txt", ".pdf"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(allowed))}",
        )

    # Sanitize: keep only the base name (no path separators) to prevent traversal
    safe_name = Path(file.filename or "upload").name
    # Strip any remaining directory components and replace non-safe characters
    safe_name = re.sub(r"[^\w\s.\-]", "_", safe_name)

    dest_dir = REPO_ROOT / "raw" / "sources"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_name

    # Enforce a 50 MB size limit to avoid memory exhaustion
    max_bytes = 50 * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail="Uploaded file exceeds the 50 MB limit.",
        )
    dest_path.write_bytes(content)

    ingest_script = REPO_ROOT / "tools" / "ingest.py"
    result = subprocess.run(
        [sys.executable, str(ingest_script), "--embed"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Ingest failed:\n{result.stderr or result.stdout}",
        )

    try:
        from core import retriever
        retriever.invalidate_cache()
    except Exception:
        pass

    return IngestResponse(
        status="ok",
        message=result.stdout.strip() or f"File '{file.filename}' ingested successfully.",
    )


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    """Serve the single-page web dashboard at the root URL.

    Returns
    -------
    The ``dashboard/index.html`` file as an HTML response.
    """
    index_path = REPO_ROOT / "dashboard" / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found.")
    return FileResponse(str(index_path), media_type="text/html")

