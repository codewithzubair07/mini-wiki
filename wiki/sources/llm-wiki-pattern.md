---
title: "LLM Wiki Pattern"
type: source
tags: [knowledge-management, llm, second-brain]
created: 2026-04-20
updated: 2026-04-20
original_file: raw/sources/llm-wiki-pattern.md
---

# Source: LLM Wiki Pattern

## Summary
An idea document describing the LLM Wiki pattern — a method for building personal knowledge bases where an LLM incrementally maintains a structured wiki from raw source documents, rather than using classic RAG retrieval at query time. The document covers architecture, operations (ingest, query, lint), tooling suggestions, and example use cases.

## Key Claims
- RAG retrieves chunks at query time; LLM Wiki compiles knowledge once and maintains it persistently
- The wiki has three layers: raw sources (immutable), the wiki (LLM-owned markdown), and a schema (agent instructions)
- A single ingest may update 10–15 wiki pages across entities, concepts, and summaries
- Good query answers can be filed back into the wiki as synthesis pages
- The schema file (AGENTS.md) is what makes the LLM a disciplined wiki maintainer rather than a generic chatbot
- `index.md` (content-oriented catalog) and `log.md` (chronological history) are the two special navigation files
- The Memex (Vannevar Bush, 1945) is an intellectual ancestor of this pattern

## Extracted Entities
- [[Vannevar Bush]]

## Extracted Concepts
- [[LLM Wiki]]
- [[Retrieval-Augmented Generation]]

## Notes
This is an example source created to seed the wiki with initial content. Replace it with your own source documents in `raw/sources/`.
