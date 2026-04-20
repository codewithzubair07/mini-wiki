#!/usr/bin/env python3
"""
lint.py — Check the wiki for health issues.

Usage:
    python tools/lint.py
    python tools/lint.py --fix        # auto-fix what can be fixed automatically

Checks:
    - Orphan pages: wiki pages with no inbound [[wikilinks]] from other pages
    - Broken links: [[wikilinks]] that reference pages that don't exist
    - Empty pages: pages with no content beyond frontmatter
    - Duplicate candidates: pages with very similar titles

Exit codes:
    0 — no issues found
    1 — issues found (or internal error)
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
LOG_FILE = WIKI_DIR / "log.md"
INDEX_FILE = WIKI_DIR / "index.md"

SKIP_FILES = {"index.md", "log.md"}


def get_all_wiki_pages() -> list[Path]:
    """Return all wiki markdown files excluding index and log."""
    return [
        p
        for p in WIKI_DIR.rglob("*.md")
        if p.name not in SKIP_FILES
    ]


def slug_from_path(path: Path) -> str:
    return path.stem


def extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wikilink]] targets from a markdown file."""
    return re.findall(r'\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]', content)


def extract_title(content: str, fallback: str) -> str:
    fm_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    if fm_match:
        return fm_match.group(1).strip()
    h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()
    return fallback


def has_real_content(content: str) -> bool:
    """Check if a page has content beyond frontmatter and empty sections."""
    # Remove frontmatter
    stripped = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL).strip()
    # Remove headings
    stripped = re.sub(r'^#+\s.*$', '', stripped, flags=re.MULTILINE)
    # Remove TODO markers
    stripped = re.sub(r'_TODO.*?_', '', stripped)
    stripped = re.sub(r'_None yet\._', '', stripped)
    stripped = stripped.strip()
    return len(stripped) > 20


def slugify_title(title: str) -> str:
    """Convert a title to slug format for comparison."""
    title = title.lower()
    title = re.sub(r'[^\w\s-]', '', title)
    title = re.sub(r'[\s_]+', '-', title)
    return title.strip('-')


def find_duplicate_candidates(pages: list[Path]) -> list[tuple[Path, Path, float]]:
    """Find pages with very similar titles."""
    page_titles = {}
    for page in pages:
        content = page.read_text(encoding="utf-8")
        title = extract_title(content, page.stem)
        page_titles[page] = title

    duplicates = []
    items = list(page_titles.items())
    for i, (path_a, title_a) in enumerate(items):
        for path_b, title_b in items[i + 1 :]:
            slug_a = slugify_title(title_a)
            slug_b = slugify_title(title_b)
            # Simple prefix/substring similarity
            if slug_a == slug_b:
                duplicates.append((path_a, path_b, 1.0))
            elif slug_a in slug_b or slug_b in slug_a:
                overlap = min(len(slug_a), len(slug_b)) / max(len(slug_a), len(slug_b))
                if overlap > 0.8:
                    duplicates.append((path_a, path_b, overlap))
    return duplicates


def build_link_graph(pages: list[Path]) -> tuple[dict, dict]:
    """
    Build inbound and outbound link graphs.
    Returns (inbound_links, outbound_links) where keys are slugs.
    """
    inbound: dict[str, list[str]] = defaultdict(list)
    outbound: dict[str, list[str]] = defaultdict(list)

    # Build slug → path map (case-insensitive)
    slug_map: dict[str, str] = {}
    for page in pages:
        content = page.read_text(encoding="utf-8")
        title = extract_title(content, page.stem)
        # Map both slug-of-title and filename slug
        slug_map[slugify_title(title)] = page.stem
        slug_map[page.stem] = page.stem

    all_slugs = {p.stem for p in pages}

    for page in pages:
        content = page.read_text(encoding="utf-8")
        links = extract_wikilinks(content)
        for link in links:
            # Normalize the link to a slug
            link_slug = slugify_title(link)
            resolved = slug_map.get(link_slug) or slug_map.get(link.lower().replace(" ", "-"))
            if resolved is None:
                # Try direct match
                direct = link.lower().replace(" ", "-")
                resolved = direct if direct in all_slugs else None

            target_slug = resolved if resolved else link_slug
            outbound[page.stem].append(target_slug)
            inbound[target_slug].append(page.stem)

    return dict(inbound), dict(outbound)


def run_lint(fix: bool = False) -> int:
    """Run all lint checks and report issues. Returns number of issues found."""
    pages = get_all_wiki_pages()
    if not pages:
        print("No wiki pages found.")
        return 0

    all_slugs = {p.stem for p in pages}
    issues = 0

    print(f"Linting {len(pages)} wiki pages...\n")

    # --- Build link graph ---
    inbound, outbound = build_link_graph(pages)

    # --- 1. Broken links ---
    broken_links: list[tuple[str, str]] = []
    for page in pages:
        targets = outbound.get(page.stem, [])
        for target in targets:
            if target not in all_slugs:
                broken_links.append((page.stem, target))

    if broken_links:
        issues += len(broken_links)
        print(f"⚠️  Broken links ({len(broken_links)}):")
        for source, target in broken_links:
            print(f"   {source}.md → [[{target}]] (target not found)")
        print()
    else:
        print("✅  No broken links")

    # --- 2. Orphan pages ---
    orphans = [
        p for p in pages
        if p.stem not in inbound or not inbound[p.stem]
    ]

    if orphans:
        issues += len(orphans)
        print(f"\n⚠️  Orphan pages ({len(orphans)}) — no inbound links from other wiki pages:")
        for p in orphans:
            content = p.read_text(encoding="utf-8")
            title = extract_title(content, p.stem)
            print(f"   {p.relative_to(REPO_ROOT)}  ({title})")
        print()
    else:
        print("✅  No orphan pages")

    # --- 3. Empty pages ---
    empty_pages = []
    for page in pages:
        content = page.read_text(encoding="utf-8")
        if not has_real_content(content):
            empty_pages.append(page)

    if empty_pages:
        issues += len(empty_pages)
        print(f"\n⚠️  Empty / stub pages ({len(empty_pages)}):")
        for p in empty_pages:
            print(f"   {p.relative_to(REPO_ROOT)}")
        print()
    else:
        print("✅  No empty pages")

    # --- 4. Duplicate candidates ---
    duplicates = find_duplicate_candidates(pages)
    if duplicates:
        issues += len(duplicates)
        print(f"\n⚠️  Possible duplicate pages ({len(duplicates)}):")
        for path_a, path_b, score in duplicates:
            content_a = path_a.read_text(encoding="utf-8")
            content_b = path_b.read_text(encoding="utf-8")
            title_a = extract_title(content_a, path_a.stem)
            title_b = extract_title(content_b, path_b.stem)
            print(f"   {path_a.relative_to(REPO_ROOT)} ({title_a!r})")
            print(f"   {path_b.relative_to(REPO_ROOT)} ({title_b!r})")
            print(f"   similarity: {score:.0%}")
            print()
    else:
        print("✅  No duplicate candidates")

    # --- Summary ---
    print("\n" + "─" * 50)
    if issues == 0:
        print("✅  Wiki looks healthy!")
    else:
        print(f"⚠️  {issues} issue(s) found.")
        print(
            "\nTo fix, open this repo in your LLM agent and ask it to:\n"
            "  'Run the lint workflow described in schema/AGENTS.md and fix the issues.'"
        )

    # --- Append to log ---
    from datetime import date  # noqa: PLC0415

    today = date.today().isoformat()
    log_entry = (
        f"\n## [{today}] lint | Wiki health check\n"
        f"- Pages checked: {len(pages)}\n"
        f"- Broken links: {len(broken_links)}\n"
        f"- Orphan pages: {len(orphans)}\n"
        f"- Empty pages: {len(empty_pages)}\n"
        f"- Duplicate candidates: {len(duplicates)}\n"
    )
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(log_entry)

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint the wiki for health issues.")
    parser.add_argument(
        "--fix", action="store_true", help="Auto-fix issues where possible (not yet implemented)"
    )
    args = parser.parse_args()

    if not WIKI_DIR.exists():
        print(f"Error: wiki directory not found at {WIKI_DIR}", file=sys.stderr)
        return 1

    issues = run_lint(fix=args.fix)
    return 0 if issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
