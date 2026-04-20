---
title: "LLM Wiki vs RAG: A Comparison"
type: synthesis
tags: [knowledge-management, llm, rag, comparison]
created: 2026-04-20
updated: 2026-04-20
sources: [llm-wiki-pattern]
---

# LLM Wiki vs RAG: A Comparison

## Overview
Both RAG and LLM Wiki use language models to answer questions over a document collection. They differ fundamentally in *when* knowledge is processed and *whether* it accumulates.

## Key Findings
- RAG processes knowledge at query time; LLM Wiki processes it at ingest time
- LLM Wiki produces a persistent, compounding artifact; RAG produces transient answers
- LLM Wiki is better suited for long-running research and synthesis; RAG is simpler for one-off Q&A
- Both can be combined: use RAG to find relevant wiki pages, then synthesize from them

## Comparison

| Dimension | RAG | LLM Wiki |
|-----------|-----|----------|
| When is knowledge processed? | At query time | At ingest time |
| Does knowledge accumulate? | No | Yes |
| Cross-references | Implicit (chunk similarity) | Explicit (maintained wikilinks) |
| Contradictions | Not tracked | Flagged and noted |
| Infrastructure | Embedding store + retrieval | Plain markdown files in git |
| Maintenance cost | Low upfront, repeated per query | Higher upfront, amortized over queries |
| Best for | Simple factual Q&A | Long-running research and synthesis |

## Open Questions
- At what wiki size does RAG over the wiki pages become necessary?
- Can the two be combined effectively (RAG → wiki pages → synthesis)?

## Related Pages
- [[LLM Wiki]]
- [[Retrieval-Augmented Generation]]

## Sources
- [[llm-wiki-pattern]]
