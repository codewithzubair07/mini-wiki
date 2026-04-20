---
title: "Retrieval-Augmented Generation"
type: concept
tags: [llm, rag, information-retrieval]
created: 2026-04-20
updated: 2026-04-20
sources: [llm-wiki-pattern]
---

# Retrieval-Augmented Generation

## Summary
Retrieval-Augmented Generation (RAG) is a technique where a language model retrieves relevant chunks from a document collection at query time and uses those chunks to generate a grounded answer. It is widely used in document Q&A systems, chatbots, and enterprise search.

## Why It Matters
RAG is the dominant pattern for LLM + document systems today (NotebookLM, ChatGPT file uploads, most enterprise search tools). Understanding it clarifies what the [[LLM Wiki]] pattern is doing differently and why.

## Key Claims
- RAG retrieves document chunks at query time; no knowledge is accumulated between queries (source: [[llm-wiki-pattern]])
- RAG must re-derive answers from raw sources on every question (source: [[llm-wiki-pattern]])
- For simple factual lookups RAG works well; for synthesis across many documents it must repeatedly find and piece together fragments (source: [[llm-wiki-pattern]])

## Contradictions / Open Questions
- For small, well-structured document sets RAG may be simpler and sufficient — the overhead of maintaining a wiki may not be worth it.

## Related Pages
- [[LLM Wiki]] (the LLM Wiki pattern as an alternative/complement to RAG)

## Sources
- [[llm-wiki-pattern]]
