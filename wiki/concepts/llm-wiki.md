---
title: "LLM Wiki"
type: concept
tags: [knowledge-management, llm, wiki, second-brain]
created: 2026-04-20
updated: 2026-04-20
sources: [llm-wiki-pattern]
---

# LLM Wiki

## Summary
An LLM Wiki is a persistent, LLM-maintained knowledge base built from raw source documents. Instead of retrieving raw chunks at query time (as in RAG), the LLM incrementally builds and updates a structured wiki — creating entity and concept pages, maintaining cross-references, flagging contradictions, and accumulating syntheses.

## Why It Matters
Knowledge **accumulates** rather than being rediscovered on every query. Cross-references are pre-built. Contradictions are flagged. The synthesis already reflects everything you've read. This makes the wiki progressively more valuable over time, unlike RAG systems where nothing is retained between sessions.

## Key Claims
- The LLM owns the wiki layer; the human curates sources and asks questions (source: [[llm-wiki-pattern]])
- A single source ingest may update 10–15 wiki pages (source: [[llm-wiki-pattern]])
- Answers to good questions can be promoted into synthesis pages, compounding the knowledge base (source: [[llm-wiki-pattern]])
- The schema file (AGENTS.md / CLAUDE.md) is the key configuration that makes an LLM a disciplined wiki maintainer rather than a generic chatbot (source: [[llm-wiki-pattern]])

## Contradictions / Open Questions
- At what scale does reading `index.md` first break down compared to embedding-based search?
- How should contradictions between sources be resolved vs. just flagged?

## Related Pages
- [[Retrieval-Augmented Generation]]
- [[Vannevar Bush]]
- [[Zettelkasten]]
- [[Niklas Luhmann]]
- [[LLM Wiki vs RAG: A Comparison]] (synthesis)

## Sources
- [[llm-wiki-pattern]]
