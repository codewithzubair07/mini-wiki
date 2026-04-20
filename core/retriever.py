"""
retriever.py — FAISS-backed semantic retriever for mini-wiki.

Responsibilities:
- Load (or create) the FAISS vector index from ``vectorstore/``.
- Embed an incoming query using the same sentence-transformers model that was
  used at ingest time.
- Return the top-k most similar chunks together with their source metadata.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from core._settings import get_settings

# ---------------------------------------------------------------------------
# Module-level singletons (loaded lazily, shared across requests)
# ---------------------------------------------------------------------------
_model: SentenceTransformer | None = None
_index: faiss.Index | None = None
_metadata: list[dict[str, Any]] = []


def _get_model() -> SentenceTransformer:
    """Return the singleton embedding model (loaded once)."""
    global _model
    if _model is None:
        settings = get_settings()
        model_name: str = settings["embedding"]["model"]
        _model = SentenceTransformer(model_name)
    return _model


def _vectorstore_paths() -> tuple[Path, Path]:
    """Return paths to the FAISS index file and metadata JSON file."""
    settings = get_settings()
    repo_root = Path(__file__).resolve().parent.parent
    vs_dir = repo_root / settings["retrieval"]["vectorstore_dir"]
    return vs_dir / "index.faiss", vs_dir / "metadata.json"


def load_index() -> tuple[faiss.Index, list[dict[str, Any]]]:
    """Load the FAISS index and metadata from disk.

    Returns
    -------
    index : faiss.Index
        The loaded FAISS flat inner-product index.
    metadata : list[dict]
        Per-chunk metadata dicts with keys ``source``, ``text``, etc.

    Raises
    ------
    FileNotFoundError
        If the vector store has not been built yet (run ``/ingest`` first).
    """
    global _index, _metadata

    index_path, meta_path = _vectorstore_paths()

    if not index_path.exists() or not meta_path.exists():
        raise FileNotFoundError(
            "Vector store not found. Call POST /ingest to build it first."
        )

    _index = faiss.read_index(str(index_path))
    with meta_path.open("r", encoding="utf-8") as fh:
        _metadata = json.load(fh)

    return _index, _metadata


def retrieve(query: str, top_k: int | None = None) -> list[dict[str, Any]]:
    """Retrieve the top-k most relevant chunks for *query*.

    Parameters
    ----------
    query : str
        Natural-language question from the user.
    top_k : int | None
        Number of chunks to return.  Defaults to the value in
        ``config/settings.yml`` (``retrieval.top_k``).

    Returns
    -------
    list[dict]
        Each item has keys: ``text``, ``source``, ``score`` (inner-product
        similarity score; higher values indicate better matches).
    """
    global _index, _metadata

    settings = get_settings()
    if top_k is None:
        top_k = int(settings["retrieval"]["top_k"])

    # Load index lazily (first call or after a fresh ingest)
    if _index is None:
        load_index()

    model = _get_model()
    query_vec: np.ndarray = model.encode([query], normalize_embeddings=True)

    distances, indices = _index.search(query_vec.astype("float32"), top_k)

    results: list[dict[str, Any]] = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx == -1:
            # FAISS returns -1 when fewer than top_k results exist
            continue
        chunk_meta = _metadata[idx].copy()
        chunk_meta["score"] = float(dist)
        results.append(chunk_meta)

    return results


def invalidate_cache() -> None:
    """Force the next ``retrieve`` call to reload the index from disk.

    Call this after rebuilding the vector store via ``/ingest``.
    """
    global _index, _metadata
    _index = None
    _metadata = []
