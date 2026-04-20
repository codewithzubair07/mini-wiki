#!/usr/bin/env python3
"""
ingest.py — Ingest a source file into the wiki.

Usage:
    python tools/ingest.py <path-to-source-file> [--dry-run]

What it does:
    1. Validates the source file exists and is in raw/sources/
    2. Creates a source summary page in wiki/sources/ (stub, for LLM to fill)
    3. Appends an ingest entry to wiki/log.md
    4. Prints a prompt you can paste into your LLM agent to complete the ingest

For full LLM-assisted ingest, open this repo in Claude/Codex and ask it to
run the ingest workflow described in schema/AGENTS.md.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
RAW_SOURCES = REPO_ROOT / "raw" / "sources"
LOG_FILE = WIKI_DIR / "log.md"
INDEX_FILE = WIKI_DIR / "index.md"


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a source file into the wiki.")
    parser.add_argument("source", help="Path to the source file to ingest")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would happen without writing files"
    )
    args = parser.parse_args()

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
