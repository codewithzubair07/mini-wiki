#!/usr/bin/env python3
"""
ingest.py — Ingest wiki markdown files into a FAISS vector store.

The script now has two modes:

1. **Classic wiki-stub mode** (original behaviour, preserved):
       python tools/ingest.py <path-to-source-file> [--dry-run]
   Creates a stub wiki page, updates log.md and index.md, and prints an LLM
   prompt to fill the stub in.

2. **Embedding pipeline mode** (new — builds the RAG vector store):
       python tools/ingest.py --embed
   Reads every *.md file under wiki/, chunks the text, generates embeddings
   with sentence-transformers, and saves a FAISS index to vectorstore/.

For full LLM-assisted ingest, open this repo in Claude/Codex and ask it to
run the ingest workflow described in schema/AGENTS.md.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
RAW_SOURCES = REPO_ROOT / "raw" / "sources"
LOG_FILE = WIKI_DIR / "log.md"
INDEX_FILE = WIKI_DIR / "index.md"


# ---------------------------------------------------------------------------
# Helpers shared by both modes
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert a string to a filesystem-safe slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = text.strip("-")
    return text


def title_from_path(path: Path) -> str:
    """Derive a human-readable title from a file path."""
    stem = path.stem
    title = stem.replace("-", " ").replace("_", " ").title()
    return title


# ---------------------------------------------------------------------------
# Classic wiki-stub helpers (original ingest.py logic, unchanged)
# ---------------------------------------------------------------------------

def create_source_page(source_path: Path, dry_run: bool = False) -> Path:
    """Create a stub source summary page in wiki/sources/."""
    title = title_from_path(source_path)
    slug = slugify(source_path.stem)
    today = date.today().isoformat()
    try:
        relative_source = source_path.relative_to(REPO_ROOT)
    except ValueError:
        relative_source = Path("raw") / "sources" / source_path.name

    content = f"""---
title: "{title}"
type: source
tags: []
created: {today}
updated: {today}
original_file: {relative_source}
---

# Source: {title}

## Summary
_TODO: Add a 2–4 sentence summary of this source._

## Key Claims
- _TODO: List the key claims made in this source._

## Extracted Entities
- _TODO: List entities (people, projects, companies) mentioned._

## Extracted Concepts
- _TODO: List concepts and ideas covered._

## Notes
_TODO: Add any caveats, context, or quality notes._
"""

    dest = WIKI_DIR / "sources" / f"{slug}.md"

    if dest.exists():
        print(f"  Source page already exists: {dest.relative_to(REPO_ROOT)}")
        return dest

    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        print(f"  Created: {dest.relative_to(REPO_ROOT)}")
    else:
        print(f"  [dry-run] Would create: {dest.relative_to(REPO_ROOT)}")

    return dest


def append_log_entry(source_path: Path, source_page: Path, dry_run: bool = False) -> None:
    """Append an ingest entry to wiki/log.md."""
    title = title_from_path(source_path)
    today = date.today().isoformat()
    slug = slugify(source_path.stem)

    try:
        source_rel = source_path.relative_to(REPO_ROOT)
    except ValueError:
        source_rel = Path("raw") / "sources" / source_path.name

    entry = f"""
## [{today}] ingest | {title}
- Source file: {source_rel}
- Pages created: {source_page.relative_to(REPO_ROOT)}
- Pages updated: wiki/index.md, wiki/log.md
- Entities: _TODO_
- Concepts: _TODO_
- Notes: Stub created by ingest.py; use LLM agent to complete (see schema/AGENTS.md)
"""

    if not dry_run:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(entry)
        print(f"  Appended to: {LOG_FILE.relative_to(REPO_ROOT)}")
    else:
        print(f"  [dry-run] Would append to: {LOG_FILE.relative_to(REPO_ROOT)}")


def append_index_entry(source_path: Path, dry_run: bool = False) -> None:
    """Add a stub row to the Sources table in wiki/index.md."""
    title = title_from_path(source_path)
    slug = slugify(source_path.stem)
    today = date.today().isoformat()

    new_row = f"| [[{slug}]] | _TODO: one-line summary_ | {today} |"

    if not INDEX_FILE.exists():
        print(f"  Warning: {INDEX_FILE.relative_to(REPO_ROOT)} not found; skipping index update")
        return

    content = INDEX_FILE.read_text(encoding="utf-8")

    # Insert before the Entities section (or at end of Sources table)
    if new_row in content:
        print(f"  Index entry already present for: {slug}")
        return

    # Find the Sources table and append the row before the next ## section
    pattern = r"(## Sources\n\|.*?\|\n\|.*?\|\n)((?:\|.*?\|\n)*)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        updated = content[: match.end(2)] + new_row + "\n" + content[match.end(2) :]
    else:
        # Fallback: append after the Sources header if table not found
        sources_pos = content.find("## Sources\n")
        if sources_pos != -1:
            insert_pos = content.find("\n## ", sources_pos + 1)
            if insert_pos == -1:
                insert_pos = len(content)
            updated = content[:insert_pos] + new_row + "\n" + content[insert_pos:]
        else:
            updated = content + f"\n{new_row}\n"

    if not dry_run:
        INDEX_FILE.write_text(updated, encoding="utf-8")
        print(f"  Updated: {INDEX_FILE.relative_to(REPO_ROOT)}")
    else:
        print(f"  [dry-run] Would update: {INDEX_FILE.relative_to(REPO_ROOT)}")


def print_llm_prompt(source_path: Path) -> None:
    """Print a prompt the user can paste into their LLM agent."""
    try:
        relative = source_path.relative_to(REPO_ROOT)
    except ValueError:
        relative = Path("raw") / "sources" / source_path.name
    print(
        f"""
╔══════════════════════════════════════════════════════════════╗
║  LLM Agent Prompt (paste into Claude / Codex / your agent)  ║
╚══════════════════════════════════════════════════════════════╝

Read schema/AGENTS.md to understand the wiki conventions, then
fully ingest the source at {relative}:

1. Read the source file.
2. Update wiki/sources/{slugify(source_path.stem)}.md with a proper summary.
3. Create or update relevant entity pages in wiki/entities/.
4. Create or update relevant concept pages in wiki/concepts/.
5. Update wiki/index.md.
6. Update wiki/log.md with a complete ingest entry.
"""
    )


# ---------------------------------------------------------------------------
# Embedding pipeline helpers
# ---------------------------------------------------------------------------

def _load_settings() -> dict[str, Any]:
    """Load config/settings.yml without pulling in the full core package."""
    import yaml  # available after pip install PyYAML

    settings_path = REPO_ROOT / "config" / "settings.yml"
    with settings_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter block from markdown text."""
    return re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL).strip()


def _chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """Split *text* into overlapping chunks of approximately *chunk_size* words.

    Uses a simple word-count heuristic (1 token ≈ 0.75 words for English
    prose) to stay within the 300–500 token target range without requiring a
    tokeniser as a dependency.

    Parameters
    ----------
    text : str
        Plain text to chunk (frontmatter already stripped).
    chunk_size : int
        Target chunk size measured in words (roughly 300–500 tokens for
        English prose, given ~0.75 words per token).
    overlap : int
        Number of words to overlap between consecutive chunks.

    Returns
    -------
    list[str]
        Non-empty text chunks.
    """
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end == len(words):
            break
        start += chunk_size - overlap

    return chunks


def run_embedding_pipeline() -> None:
    """Read all wiki markdown files, embed them, and save a FAISS index.

    The resulting files are written to the ``vectorstore/`` directory:
    - ``vectorstore/index.faiss`` — FAISS flat inner-product index.
    - ``vectorstore/metadata.json`` — per-chunk metadata (source, text).
    """
    try:
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        print(
            f"Error: missing dependency ({exc}). "
            "Run: pip install faiss-cpu sentence-transformers",
            file=sys.stderr,
        )
        sys.exit(1)

    settings = _load_settings()
    embedding_model_name: str = settings["embedding"]["model"]
    chunk_size: int = int(settings["ingest"]["chunk_size"])
    chunk_overlap: int = int(settings["ingest"]["chunk_overlap"])
    vs_dir: Path = REPO_ROOT / settings["retrieval"]["vectorstore_dir"]

    print(f"Loading embedding model: {embedding_model_name}")
    model = SentenceTransformer(embedding_model_name)

    # Collect all markdown files under wiki/
    md_files = sorted(WIKI_DIR.rglob("*.md"))
    if not md_files:
        print("No markdown files found in wiki/. Nothing to ingest.")
        return

    print(f"Found {len(md_files)} markdown file(s) under wiki/")

    all_chunks: list[str] = []
    all_meta: list[dict[str, Any]] = []

    for md_file in md_files:
        raw = md_file.read_text(encoding="utf-8")
        text = _strip_frontmatter(raw)
        chunks = _chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap)

        source_name = md_file.relative_to(REPO_ROOT).as_posix()
        for chunk in chunks:
            all_chunks.append(chunk)
            all_meta.append({"source": source_name, "text": chunk})

        print(f"  {source_name}: {len(chunks)} chunk(s)")

    if not all_chunks:
        print("No text chunks produced. Check that wiki/ files contain content.")
        return

    print(f"\nGenerating embeddings for {len(all_chunks)} chunk(s)…")
    embeddings: np.ndarray = model.encode(
        all_chunks,
        show_progress_bar=True,
        normalize_embeddings=True,
        batch_size=64,
    )

    # Build a flat inner-product index (cosine similarity after normalisation)
    dim: int = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings.astype("float32"))

    # Persist to disk
    vs_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(vs_dir / "index.faiss"))
    with (vs_dir / "metadata.json").open("w", encoding="utf-8") as fh:
        json.dump(all_meta, fh, ensure_ascii=False, indent=2)

    print(
        f"\nVector store saved to {vs_dir.relative_to(REPO_ROOT)}/\n"
        f"  index.faiss  — {index.ntotal} vectors (dim={dim})\n"
        f"  metadata.json — {len(all_meta)} entries"
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest a source file into the wiki, or build the RAG vector store."
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="Path to the source file to ingest (classic stub mode)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without writing files (classic mode only)",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Build/rebuild the FAISS embedding index from wiki/ markdown files",
    )
    args = parser.parse_args()

    # --- Embedding pipeline mode ---
    if args.embed:
        run_embedding_pipeline()
        return 0

    # --- Classic wiki-stub mode ---
    if not args.source:
        parser.print_help()
        return 1

    source_path = Path(args.source).resolve()

    if not source_path.exists():
        print(f"Error: file not found: {args.source}", file=sys.stderr)
        return 1

    if not source_path.is_file():
        print(f"Error: not a file: {args.source}", file=sys.stderr)
        return 1

    # Warn if outside raw/sources but don't block it
    try:
        source_path.relative_to(RAW_SOURCES)
    except ValueError:
        print(
            f"Warning: {source_path} is not inside raw/sources/. "
            "Consider moving raw sources there to keep them immutable.",
            file=sys.stderr,
        )

    print(f"\nIngesting: {source_path.name}")
    print("-" * 40)

    source_page = create_source_page(source_path, dry_run=args.dry_run)
    append_log_entry(source_path, source_page, dry_run=args.dry_run)
    append_index_entry(source_path, dry_run=args.dry_run)

    print("-" * 40)
    print("Stub pages created. Run the LLM prompt below to complete the ingest.\n")

    print_llm_prompt(source_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

