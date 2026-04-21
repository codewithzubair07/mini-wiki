"""
generator.py — LLM answer generation for mini-wiki.

Supports two back-ends controlled by ``config/settings.yml``:
- ``openai``  — calls the OpenAI Chat Completions API (requires OPENAI_API_KEY).
- ``ollama``  — calls a locally running Ollama instance via its HTTP API.

The prompt is strictly grounded: the LLM is instructed to answer only from the
provided context and to say "I don't know" when the context is insufficient.
"""

from __future__ import annotations

import os

import httpx

from core._settings import get_settings

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a helpful assistant for a personal wiki. "
    "Answer questions strictly based on the context provided below. "
    "If the answer is not contained in the context, say \"I don't know\". "
    "Be concise and accurate."
)

_USER_TEMPLATE = """\
{history}Context:
{context}

Question: {question}

Instructions:
- Answer only from the context above.
- If the context does not contain the answer, respond with "I don't know".
- Be concise and accurate.
"""


def build_prompt(
    question: str,
    chunks: list[str],
    history: list[dict[str, str]] | None = None,
) -> str:
    """Combine retrieved *chunks*, optional *history*, and *question* into a grounded prompt.

    Parameters
    ----------
    question : str
        The user's natural-language query.
    chunks : list[str]
        Retrieved text chunks from the wiki.
    history : list[dict[str, str]] | None
        Prior conversation turns (``[{"user": ..., "assistant": ...}, ...]``).
        When provided, the history is prepended to the prompt so the LLM can
        take prior context into account.

    Returns
    -------
    str
        Formatted user message for the LLM.
    """
    context = "\n\n---\n\n".join(chunks)

    history_text = ""
    if history:
        lines = ["Previous conversation:"]
        for turn in history:
            lines.append(f"User: {turn['user']}")
            lines.append(f"Assistant: {turn['assistant']}")
        history_text = "\n".join(lines) + "\n\n"

    return _USER_TEMPLATE.format(history=history_text, context=context, question=question)


# ---------------------------------------------------------------------------
# OpenAI back-end
# ---------------------------------------------------------------------------

def _call_openai(prompt: str) -> str:
    """Call the OpenAI Chat Completions API and return the answer text."""
    import openai  # imported lazily so openai is only required when used

    settings = get_settings()
    model: str = settings["llm"]["model"]

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY environment variable is not set. "
            "Export it before starting the server."
        )

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Ollama back-end
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str) -> str:
    """Call a locally running Ollama server and return the answer text."""
    settings = get_settings()
    model: str = settings["llm"]["model"]
    base_url: str = settings["llm"].get("ollama_base_url", "http://localhost:11434")

    # Build the full message list including the system prompt
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{base_url}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        resp.raise_for_status()

    data = resp.json()
    return data["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def generate(
    question: str,
    chunks: list[str],
    history: list[dict[str, str]] | None = None,
) -> str:
    """Generate a grounded answer for *question* given *chunks* as context.

    Selects the LLM back-end from ``config/settings.yml`` (``llm.provider``).

    Parameters
    ----------
    question : str
        The user's natural-language query.
    chunks : list[str]
        Retrieved text chunks from the wiki (used as context).
    history : list[dict[str, str]] | None
        Optional prior conversation turns to include in the prompt
        (``[{"user": ..., "assistant": ...}, ...]``).

    Returns
    -------
    str
        The LLM's answer, grounded in the provided context.
    """
    settings = get_settings()
    provider: str = settings["llm"]["provider"].lower()

    prompt = build_prompt(question, chunks, history=history)

    if provider == "openai":
        return _call_openai(prompt)
    elif provider == "ollama":
        return _call_ollama(prompt)
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider!r}. "
            "Set llm.provider to 'openai' or 'ollama' in config/settings.yml."
        )
