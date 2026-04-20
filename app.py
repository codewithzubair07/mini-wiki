"""
app.py — FastAPI server for mini-wiki RAG backend.

Endpoints
---------
GET  /health   — liveness / status check
POST /ingest   — build (or rebuild) the FAISS vector store from wiki/ markdown
POST /ask      — accept a natural-language query and return a grounded answer

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

import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="mini-wiki RAG API",
    description="Local-first AI assistant backed by your personal wiki.",
    version="1.0.0",
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
    sources: list[str]
    context: list[str]


class IngestResponse(BaseModel):
    """Response from POST /ingest."""

    status: str
    message: str


class HealthResponse(BaseModel):
    """Response from GET /health."""

    status: str
    vectorstore_ready: bool


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
    """Accept a natural-language query and return a grounded answer.

    The pipeline:
    1. Converts *query* to an embedding using the configured
       ``sentence-transformers`` model.
    2. Retrieves the top-k most similar wiki chunks from the FAISS index.
    3. Passes the retrieved context to the LLM to generate a grounded answer.

    Returns a JSON object with the answer, source file names, and raw context
    chunks used to produce the answer.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty.")

    try:
        from core.pipeline import ask as rag_ask

        result = rag_ask(request.query)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc) + " Call POST /ingest to build the vector store first.",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return AskResponse(
        answer=result["answer"],
        sources=result["sources"],
        context=result["context"],
    )
