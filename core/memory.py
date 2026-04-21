"""
memory.py — Short-term conversation memory for the mini-wiki agent.

Stores the last ``_MAX_HISTORY`` user/assistant exchanges in a module-level
list so that the agent can include prior context when building prompts.

Format::

    [
        {"user": "...", "assistant": "..."},
        ...
    ]
"""

from __future__ import annotations

import threading

_MAX_HISTORY = 5
_history: list[dict[str, str]] = []
_lock = threading.Lock()


def add_interaction(user: str, assistant: str) -> None:
    """Append a user/assistant exchange and trim to the last ``_MAX_HISTORY`` items.

    Parameters
    ----------
    user : str
        The user's query.
    assistant : str
        The assistant's answer.
    """
    global _history
    with _lock:
        _history.append({"user": user, "assistant": assistant})
        if len(_history) > _MAX_HISTORY:
            _history = _history[-_MAX_HISTORY:]


def get_history() -> list[dict[str, str]]:
    """Return a shallow copy of the current conversation history.

    Returns
    -------
    list[dict[str, str]]
        Each item has keys ``user`` and ``assistant``.
    """
    with _lock:
        return list(_history)


def clear() -> None:
    """Discard all stored interactions."""
    global _history
    with _lock:
        _history = []
