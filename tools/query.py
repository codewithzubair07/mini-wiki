#!/usr/bin/env python3
"""
query.py — Search wiki pages by keyword.

Usage:
    python tools/query.py "your search query"
    python tools/query.py "your query" --type concept
    python tools/query.py "your query" --limit 5

What it does:
    Performs full-text search across all wiki markdown files and returns
    ranked results with snippets. Useful for finding relevant pages before
    asking your LLM agent a question.

For deeper synthesis, open the wiki in your LLM agent and ask it to:
    1. Read wiki/index.md
    2. Find relevant pages
    3. Synthesize an answer
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = REPO_ROOT / "wiki"

# Page types mapped to their subdirectory
PAGE_TYPES = {
    "entity": WIKI_DIR / "entities",
    "concept": WIKI_DIR / "concepts",
    "source": WIKI_DIR / "sources",
    "synthesis": WIKI_DIR / "syntheses",
}


def extract_title(content: str, fallback: str) -> str:
    """Extract the title from YAML frontmatter or first H1 heading."""
    fm_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    if fm_match:
        return fm_match.group(1).strip()
    h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()
    return fallback


def get_snippet(content: str, query_terms: list[str], context: int = 120) -> str:
    """Find the best snippet of `content` that contains query terms."""
    lower = content.lower()
    best_pos = -1
    best_count = 0

    for i in range(0, len(lower), 20):
        window = lower[i : i + context * 2]
        count = sum(1 for term in query_terms if term.lower() in window)
        if count > best_count:
            best_count = count
            best_pos = i

    if best_pos == -1:
        # Fallback: strip frontmatter and return beginning
        stripped = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL).strip()
        return stripped[:context] + ("…" if len(stripped) > context else "")

    start = max(0, best_pos)
    end = min(len(content), best_pos + context * 2)
    snippet = content[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet += "…"
    return snippet


def score_file(content: str, query_terms: list[str]) -> int:
    """Score a file based on how many query terms appear and where."""
    lower = content.lower()
    score = 0
    for term in query_terms:
        t = term.lower()
        # Title match is worth more
        title_match = re.search(r'^(title:.*|#\s+.*)$', content, re.MULTILINE)
        if title_match and t in title_match.group(0).lower():
            score += 10
        count = lower.count(t)
        score += count
    return score


def search_wiki(
    query: str,
    page_type: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """Search wiki files and return ranked results."""
    query_terms = [t for t in re.split(r'\s+', query.strip()) if t]

    if not query_terms:
        return []

    # Determine which directories to search
    if page_type:
        if page_type not in PAGE_TYPES:
            raise ValueError(f"Unknown page type: {page_type}. Choose from {list(PAGE_TYPES)}")
        search_dirs = [PAGE_TYPES[page_type]]
    else:
        search_dirs = [WIKI_DIR]

    results = []
    for search_dir in search_dirs:
        for md_file in search_dir.rglob("*.md"):
            # Skip index and log
            if md_file.name in ("index.md", "log.md"):
                continue
            content = md_file.read_text(encoding="utf-8")
            score = score_file(content, query_terms)
            if score > 0:
                title = extract_title(content, md_file.stem.replace("-", " ").title())
                snippet = get_snippet(content, query_terms)
                results.append(
                    {
                        "path": md_file.relative_to(REPO_ROOT),
                        "title": title,
                        "score": score,
                        "snippet": snippet,
                    }
                )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def print_results(results: list[dict], query: str) -> None:
    """Print search results in a readable format."""
    if not results:
        print(f"No results found for: {query!r}")
        print("\nTry:")
        print("  - Using different keywords")
        print("  - Running 'python tools/ingest.py' to add more sources")
        return

    print(f"Found {len(results)} result(s) for: {query!r}\n")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title']}")
        print(f"   Path:  {result['path']}")
        print(f"   Score: {result['score']}")
        print(f"   {result['snippet']}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Search wiki pages by keyword.")
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--type",
        choices=list(PAGE_TYPES),
        help="Filter results to a specific page type",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results to return (default: 10)",
    )
    args = parser.parse_args()

    if not WIKI_DIR.exists():
        print(f"Error: wiki directory not found at {WIKI_DIR}", file=sys.stderr)
        return 1

    results = search_wiki(args.query, page_type=args.type, limit=args.limit)
    print_results(results, args.query)

    if results:
        print(
            "─" * 60 + "\n"
            "Tip: paste relevant page paths into your LLM agent with:\n"
            '  "Read schema/AGENTS.md, then answer: <your question>"\n'
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
