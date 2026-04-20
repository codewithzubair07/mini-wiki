# mini-wiki — Personal Second Brain / LLM Wiki

A **local-first, markdown-based knowledge base** where an LLM incrementally builds and maintains a persistent wiki from your raw sources.

---

## Core Idea

Instead of searching raw documents every time you ask a question (RAG), this project has an LLM **compile and maintain a structured wiki** as new sources arrive. Knowledge accumulates. Contradictions are flagged. Syntheses are reusable.

| RAG | LLM Wiki |
|-----|----------|
| Retrieve raw chunks at query time | Build a maintained wiki once, query from it |
| Answers from raw sources each time | Answers from structured, interlinked pages |
| No accumulation | Knowledge compounds over time |

---

## Repo Structure

```
mini-wiki/
├── raw/
│   ├── sources/          # Immutable source documents (articles, notes, transcripts)
│   └── assets/           # Images, PDFs, attachments
├── wiki/
│   ├── index.md          # Master catalog of all wiki pages
│   ├── log.md            # Append-only operation history
│   ├── entities/         # Pages for people, projects, companies, books
│   ├── concepts/         # Pages for ideas, themes, topics
│   ├── sources/          # One summary page per source
│   └── syntheses/        # Comparisons, analyses, overviews
├── schema/
│   └── AGENTS.md         # LLM operating instructions
├── tools/
│   ├── ingest.py         # Ingest a source into the wiki
│   ├── query.py          # Search and query wiki pages
│   └── lint.py           # Check for orphans, stale links, duplicates
├── config/
│   └── settings.yml      # Project configuration
├── requirements.txt
└── .gitignore
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your LLM API key

```bash
cp config/settings.yml config/settings.local.yml
# Edit config/settings.local.yml and add your API key
```

Or set it via environment variable:

```bash
export OPENAI_API_KEY=sk-...
# or
export ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Add a source

Drop a markdown or text file into `raw/sources/`, then run:

```bash
python tools/ingest.py raw/sources/my-article.md
```

The tool will:
- Create a summary page in `wiki/sources/`
- Update relevant entity and concept pages
- Update `wiki/index.md`
- Append an entry to `wiki/log.md`

### 4. Query the wiki

```bash
python tools/query.py "what is retrieval augmented generation?"
```

Searches wiki pages by full-text and returns ranked results with snippets.

### 5. Lint the wiki

```bash
python tools/lint.py
```

Reports:
- Orphan pages (no inbound links)
- Broken `[[wiki links]]`
- Duplicate pages (similar titles)
- Empty pages

---

## Workflows

### Ingest a source

1. Add a source file to `raw/sources/`
2. Run `python tools/ingest.py <path>`  
   — or — open the repo in Claude/Copilot/Codex and ask it to ingest the file using `schema/AGENTS.md` as its instructions

### Ask a question

Use `python tools/query.py "your question"` for full-text search.  
For deeper synthesis, open the wiki in your LLM and ask — the LLM reads `wiki/index.md` first, drills into relevant pages, and synthesizes an answer. Optionally save the answer as a new synthesis page.

### Maintain the wiki

Run `python tools/lint.py` periodically to find orphans, broken links, and stale pages.  
Then open the wiki in your LLM and ask it to fix the reported issues.

---

## Using with Obsidian

This repo is designed to work perfectly with [Obsidian](https://obsidian.md/):

1. Open the repo folder as an Obsidian vault
2. The `wiki/` folder contains all linked pages
3. Use Obsidian's **Graph View** to visualize the knowledge graph
4. Use **Obsidian Web Clipper** to quickly add web articles as raw sources
5. Use the **Dataview** plugin to query page frontmatter

**Recommended Obsidian settings:**
- Set "Attachment folder path" → `raw/assets/`
- Enable "Use `[[Wikilinks]]`" for cross-references

---

## Using with an LLM Agent

This repo ships with `schema/AGENTS.md`, which gives your LLM agent precise instructions for:
- Ingesting sources
- Updating wiki pages
- Maintaining links and backlinks
- Tracking contradictions
- Appending to the log

When starting a new chat session with your agent (Claude, Codex, etc.), simply say:

> "Read schema/AGENTS.md, then ingest raw/sources/my-file.md"

The LLM will follow the schema to maintain a consistent, well-linked wiki.

---

## Philosophy

- **Raw sources are immutable** — the LLM reads but never modifies them
- **The wiki is LLM-owned** — you read it, the LLM writes and maintains it
- **You curate, the LLM bookkeeps** — you add sources and ask questions; the LLM handles summaries, cross-references, and consistency
- **Local-first** — everything is plain markdown in git; no database, no cloud dependency
- **Progressive complexity** — start simple, extend as needed

Inspired by Vannevar Bush's *Memex* (1945) — a personal, curated knowledge store with associative trails. The part he couldn't solve was who does the maintenance. The LLM handles that.

---

## Extending

- Add **semantic search** using `sentence-transformers` or `openai` embeddings
- Add a **web UI** with Flask or FastAPI
- Set up an **MCP server** to expose tools to your agent
- Add **automatic contradiction detection** with LLM calls
- Add **Dataview frontmatter** for dynamic Obsidian tables
