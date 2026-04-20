"""
_settings.py — Load and cache config/settings.yml.

All core modules import ``get_settings()`` from here so that the YAML file is
parsed only once per process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yml"


@lru_cache(maxsize=1)
def get_settings() -> dict[str, Any]:
    """Return the parsed contents of ``config/settings.yml`` (cached)."""
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
