"""
web_ingest.py — Web research and ingestion pipeline for mini-wiki.

Combines the BrowserClient (PinchTab) with the existing ingest pipeline to
fetch live web content and add it to the wiki knowledge base.

Typical usage::

    from tools.web_ingest import web_ingest

    summary = web_ingest("retrieval augmented generation", max_sources=3)
    # {
    #   "query": "retrieval augmented generation",
    #   "sources_ingested": 2,
    #   "files_created": ["web_retrieval-augmented-generation_0_1714000000.md"],
    #   "contradictions_found": 0,
    # }
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from core._settings import get_settings
from tools.browse import BrowserClient

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directory where fetched web source files are saved before ingestion.
_WEB_SOURCES_DIR = REPO_ROOT / "raw" / "sources" / "web"


def _sanitize_query(query: str) -> str:
    """Convert *query* into a filesystem-safe identifier string.

    Parameters
    ----------
    query : str
        The raw user query.

    Returns
    -------
    str
        Lower-cased, hyphenated slug (max 50 characters) suitable for use in
        a filename.
    """
    slug = query.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    return slug[:50]


def _run_ingest_on_file(source_path: Path) -> int:
    """Run the classic wiki-stub ingest on a single file and return contradiction count.

    Invokes ``tools/ingest.py <path>`` as a subprocess so that the full
    existing ingest logic (contradiction detection, log updates, etc.) is
    applied consistently.

    Parameters
    ----------
    source_path : Path
        Absolute path to the Markdown file to ingest.

    Returns
    -------
    int
        Number of contradictions detected (0 or more).
    """
    ingest_script = REPO_ROOT / "tools" / "ingest.py"
    result = subprocess.run(
        [sys.executable, str(ingest_script), str(source_path)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    # Count CONTRADICTION markers in the combined output as a rough proxy.
    combined = (result.stdout or "") + (result.stderr or "")
    return combined.count("CONTRADICTION")


def web_ingest(query: str, max_sources: int = 3) -> dict[str, Any]:
    """Fetch web sources for *query*, save them, and run the ingest pipeline.

    Workflow:

    1. Calls :class:`~tools.browse.BrowserClient` to research the query.
    2. Saves each source as a Markdown file under ``raw/sources/web/`` with a
       predictable, timestamped filename.
    3. Calls the existing ingest pipeline on each saved file.
    4. Returns a summary dictionary.

    Parameters
    ----------
    query : str
        The research question or topic.
    max_sources : int
        Maximum number of web sources to ingest (default ``3``).  Reads
        ``browser.max_sources_per_research`` from settings if available, but
        the explicit argument takes precedence.

    Returns
    -------
    dict
        Keys:

        ``query``
            The original query string.
        ``sources_ingested``
            Number of sources successfully saved and ingested.
        ``files_created``
            List of filenames (not full paths) written to ``raw/sources/web/``.
        ``contradictions_found``
            Total contradictions detected across all ingested files.
    """
    settings = get_settings()
    browser_cfg = settings.get("browser", {})

    # Respect the settings cap when the caller passes the default value.
    settings_max = int(browser_cfg.get("max_sources_per_research", 3))
    effective_max = min(max_sources, settings_max)

    client = BrowserClient()
    sources = client.research(query, max_sources=effective_max)

    _WEB_SOURCES_DIR.mkdir(parents=True, exist_ok=True)

    slug = _sanitize_query(query)
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S%f")
    fetched_iso = now.isoformat()

    files_created: list[str] = []
    contradictions_found = 0

    for idx, source in enumerate(sources):
        filename = f"web_{slug}_{idx}_{timestamp}.md"
        file_path = _WEB_SOURCES_DIR / filename

        # Guard against path traversal: ensure the resolved path stays within
        # the intended web sources directory.
        resolved = file_path.resolve()
        if not str(resolved).startswith(str(_WEB_SOURCES_DIR.resolve())):
            continue

        # Write the content as a Markdown file with light frontmatter so the
        # existing ingest pipeline can process it normally.
        md_content = (
            f"---\n"
            f"title: \"{source['title']}\"\n"
            f"source_url: \"{source['url']}\"\n"
            f"fetched: \"{fetched_iso}\"\n"
            f"query: \"{query}\"\n"
            f"---\n\n"
            f"# {source['title']}\n\n"
            f"{source['content']}\n"
        )
        file_path.write_text(md_content, encoding="utf-8")
        files_created.append(filename)

        contradictions_found += _run_ingest_on_file(file_path)

    return {
        "query": query,
        "sources_ingested": len(files_created),
        "files_created": files_created,
        "contradictions_found": contradictions_found,
    }
