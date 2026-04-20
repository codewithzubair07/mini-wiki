# LLM Wiki Pattern

A pattern for building personal knowledge bases using LLMs.

## The Core Idea

Most people's experience with LLMs and documents looks like RAG: you upload a collection of files, the LLM retrieves relevant chunks at query time, and generates an answer. This works, but the LLM is rediscovering knowledge from scratch on every question. There's no accumulation.

The idea here is different. Instead of just retrieving from raw documents at query time, the LLM **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of markdown files that sits between you and the raw sources. When you add a new source, the LLM reads it, extracts the key information, and integrates it into the existing wiki — updating entity pages, revising topic summaries, noting where new data contradicts old claims, strengthening or challenging the evolving synthesis.

This is the key difference: **the wiki is a persistent, compounding artifact.** The cross-references are already there. The contradictions have already been flagged. The synthesis already reflects everything you've read.

## Architecture

Three layers:

1. **Raw sources** — immutable source documents. The LLM reads but never modifies them.
2. **The wiki** — LLM-generated markdown files. Summaries, entity pages, concept pages, comparisons. The LLM owns this layer entirely.
3. **The schema** — a document (AGENTS.md or CLAUDE.md) that tells the LLM how the wiki is structured and what workflows to follow.

## Operations

- **Ingest**: drop a source into the raw collection, the LLM reads it, updates 10–15 wiki pages, and appends to the log.
- **Query**: ask a question, the LLM reads `index.md`, drills into relevant pages, synthesizes an answer. Good answers can be saved as new synthesis pages.
- **Lint**: periodically check for orphan pages, stale claims, broken links, missing cross-references.

## Navigation Files

- `index.md` — content-oriented catalog, organized by category, updated on every ingest.
- `log.md` — chronological append-only record, parseable with `grep "^## \[" wiki/log.md`.

## Intellectual Heritage

Related in spirit to Vannevar Bush's **Memex** (1945) — a personal, curated knowledge store with associative trails between documents. The part Bush couldn't solve was who does the maintenance. The LLM handles that.
