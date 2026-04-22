"""
browse.py — BrowserClient wrapping PinchTab's HTTP browser automation API.

PinchTab is a lightweight HTTP server (default: http://localhost:9867) that
exposes browser automation endpoints.  This module uses those endpoints to
search DuckDuckGo and retrieve clean page text, providing live web research
for the mini-wiki agent.

Typical usage::

    from tools.browse import BrowserClient

    client = BrowserClient()
    sources = client.research("RAG retrieval augmented generation", max_sources=3)
    # [{"title": "...", "url": "...", "content": "..."}, ...]
"""

from __future__ import annotations

import re
from typing import Any

import requests

from core._settings import get_settings

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_DUCKDUCKGO_URL = "https://duckduckgo.com"

# Default timeout (seconds) for every HTTP call to PinchTab.
_REQUEST_TIMEOUT = 30


def _pinchtab_url() -> str:
    """Return the PinchTab base URL from settings."""
    settings = get_settings()
    return settings.get("browser", {}).get("pinchtab_url", "http://localhost:9867")


# ---------------------------------------------------------------------------
# BrowserClient
# ---------------------------------------------------------------------------


class BrowserClient:
    """HTTP client for PinchTab browser automation.

    All methods read ``browser.pinchtab_url`` from ``config/settings.yml`` at
    construction time so that the URL can be changed without restarting the
    server.
    """

    def __init__(self) -> None:
        """Initialise the client, reading the PinchTab base URL from settings."""
        self._base_url: str = _pinchtab_url().rstrip("/")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[dict[str, str]]:
        """Search DuckDuckGo for *query* and return the top 5 results.

        Uses PinchTab to open a browser session, navigate to DuckDuckGo,
        submit the query, and scrape the result titles and URLs.

        Parameters
        ----------
        query : str
            The search query string.

        Returns
        -------
        list[dict[str, str]]
            Up to five items, each with keys ``"title"`` and ``"url"``.
            Returns an empty list when PinchTab is unreachable or the search
            produces no results.
        """
        try:
            response = requests.post(
                f"{self._base_url}/search",
                json={"query": query, "engine": "duckduckgo", "max_results": 5},
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data: Any = response.json()
        except requests.RequestException:
            return []

        results: list[dict[str, str]] = []
        raw_items = data if isinstance(data, list) else data.get("results", [])
        for item in raw_items[:5]:
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if title and url:
                results.append({"title": title, "url": url})
        return results

    def fetch_page(self, url: str) -> str:
        """Retrieve the clean text content of *url* via PinchTab's ``/text`` endpoint.

        Parameters
        ----------
        url : str
            The fully-qualified URL to fetch.

        Returns
        -------
        str
            Plain-text content of the page.  Returns ``""`` if the page fails
            to load, returns an empty body, or PinchTab is unavailable.
        """
        try:
            response = requests.post(
                f"{self._base_url}/text",
                json={"url": url},
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data: Any = response.json()
        except requests.RequestException:
            return ""

        if isinstance(data, str):
            return data.strip()
        text = data.get("text", "") or data.get("content", "") or ""
        return text.strip()

    def research(self, query: str, max_sources: int = 3) -> list[dict[str, str]]:
        """Search for *query* and fetch the text of the top results.

        Combines :meth:`search` and :meth:`fetch_page` to build a list of
        research sources ready for ingestion.

        Parameters
        ----------
        query : str
            Research question or topic.
        max_sources : int
            Maximum number of sources to return (default ``3``).  Sources with
            empty content are skipped and do not count toward this limit.

        Returns
        -------
        list[dict[str, str]]
            Each item has keys ``"title"``, ``"url"``, and ``"content"``.
            Empty when search returns no results or all pages fail to load.
        """
        search_results = self.search(query)
        sources: list[dict[str, str]] = []

        for item in search_results:
            if len(sources) >= max_sources:
                break
            content = self.fetch_page(item["url"])
            if not content:
                continue
            sources.append(
                {
                    "title": item["title"],
                    "url": item["url"],
                    "content": content,
                }
            )

        return sources
