# mini-wiki — AI-Powered Local-First Markdown Wiki

An **AI-powered, local-first knowledge base** with a FastAPI backend and agentic intelligence. mini-wiki lets you build and query a structured, self-maintaining wiki — augmented by RAG retrieval, an autonomous agent layer, automatic contradiction detection, live web research via PinchTab, and a clean single-page dashboard UI.

---

## Core Idea

Instead of searching raw documents every time you ask a question, this project has an LLM **compile and maintain a structured wiki** as new sources arrive. An autonomous agent layer routes intent, selects tools, and can update the wiki automatically. Knowledge accumulates; contradictions are flagged; syntheses are reusable.

| Classic RAG | mini-wiki |
|-------------|-----------|
| Retrieve raw chunks at query time | Build a maintained wiki once, query from it |
| Answers from raw sources each time | Answers from structured, interlinked pages |
| No accumulation | Knowledge compounds over time |
| Single-pass response | Multi-step agentic reasoning |

---

## Features

- **RAG retrieval** — FAISS semantic search over your wiki pages (sentence-transformers embeddings)
- **Agent intent routing** — `core/agent.py` classifies each query (`search`, `synthesize`, `update`, `research`, `meta`) and selects the right tool automatically
- **Short-term memory** — `core/memory.py` keeps the last 5–10 conversation turns for contextual follow-ups
- **Automatic contradiction detection** — ingestion snapshots the old page, calls the LLM to compare versions, and flags any factual conflicts in the wiki page, `wiki/log.md`, and `wiki/contradictions.md`
- **PinchTab web research** — `tools/browse.py` drives a local Chrome instance via PinchTab to search DuckDuckGo, fetch pages, and ingest live web content through `/research`
- **Single-page dashboard UI** — `dashboard/index.html` — a self-contained HTML/CSS/JS app (no build step) with chat, file upload, web research, and a contradictions panel
- **Wiki self-improvement** — if an answer requires synthesis, the agent can write a new page to `wiki/syntheses/` and update `wiki/index.md` automatically
- **Local-first** — all data is plain markdown in git; no cloud dependency required

---

## Repo Structure

```
mini-wiki/
├── app.py                  # FastAPI server — all endpoints
├── core/
│   ├── _settings.py        # Load config/settings.yml (cached)
│   ├── agent.py            # Autonomous agent orchestrator (intent → tool → answer)
│   ├── memory.py           # Short-term conversation memory (last N turns)
│   ├── retriever.py        # FAISS semantic retriever
│   ├── generator.py        # LLM answer generator (OpenAI / Ollama)
│   └── pipeline.py         # End-to-end RAG pipeline + contradiction extraction
├── dashboard/
│   └── index.html          # Self-contained single-page web UI
├── raw/
│   ├── sources/            # Immutable source documents (articles, notes, transcripts)
│   │   └── web/            # Auto-created web research downloads
│   └── assets/             # Images, PDFs, attachments
├── wiki/
│   ├── index.md            # Master catalog of all wiki pages
│   ├── log.md              # Append-only operation history
│   ├── contradictions.md   # Auto-detected factual contradictions
│   ├── entities/           # Pages for people, projects, companies, books
│   ├── concepts/           # Pages for ideas, themes, topics
│   ├── sources/            # One summary page per source
│   └── syntheses/          # Comparisons, analyses, overviews
├── schema/
│   └── AGENTS.md           # LLM operating instructions
├── tools/
│   ├── ingest.py           # Ingest a source → wiki pages + RAG index + contradiction check
│   ├── query.py            # Full-text search over wiki pages
│   ├── lint.py             # Check for orphans, stale links, duplicates
│   ├── browse.py           # PinchTab BrowserClient (search + fetch_page + research)
│   └── web_ingest.py       # web_ingest() — research query → save files → ingest pipeline
├── config/
│   └── settings.yml        # All project configuration
├── requirements.txt
└── .gitignore
```

---

## Setup

### 1. Prerequisites

- Python 3.10+
- An OpenAI API key **or** a locally-running [Ollama](https://ollama.com/) instance
- *(Optional)* [PinchTab](https://pinchtab.com/) running on `localhost:9867` for live web research

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure settings

All tuneable options live in `config/settings.yml`:

```yaml
llm:
  provider: openai          # "openai" | "ollama"
  model: gpt-4o
  ollama_base_url: http://localhost:11434

embedding:
  model: all-MiniLM-L6-v2   # local sentence-transformers model

retrieval:
  top_k: 5
  vectorstore_dir: vectorstore

browser:
  pinchtab_url: http://localhost:9867
  max_sources_per_research: 3
  enabled: true              # set false to disable web research
```

Set your LLM credentials via environment variable (no changes to the file needed):

```bash
export OPENAI_API_KEY=sk-...
# For Ollama, no key is needed — just run `ollama serve`
```

### 4. Build the vector store

Before querying, build the FAISS index from your wiki pages:

```bash
python tools/ingest.py --embed
```

---

## Running the Server

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

| URL | Description |
|-----|-------------|
| <http://localhost:8000/> | Single-page dashboard UI |
| <http://localhost:8000/docs> | Interactive Swagger API docs |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service status and vector store readiness |
| `POST` | `/ingest` | Rebuild the FAISS vector store from `wiki/` |
| `POST` | `/ingest/file` | Upload and ingest a `.md`, `.txt`, or `.pdf` file |
| `POST` | `/ask` | Ask a question — agent-routed, grounded answer |
| `POST` | `/research` | Live web research via PinchTab + auto-ingest |
| `GET` | `/contradictions` | List all detected contradictions |

---

## Example Usage

### Ask a question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is retrieval augmented generation?"}'
```

```json
{
  "answer": "Retrieval Augmented Generation (RAG) combines a semantic retriever ...",
  "intent": "search",
  "actions_taken": ["retrieve"],
  "sources": ["wiki/concepts/retrieval-augmented-generation.md"],
  "confidence": "high",
  "context": ["RAG combines a retriever that searches a knowledge base ..."],
  "contradictions": [],
  "web_sources_ingested": 0
}
```

### Rebuild the vector store

```bash
curl -X POST http://localhost:8000/ingest
```

### Upload a file for ingestion

```bash
curl -X POST http://localhost:8000/ingest/file \
  -F "file=@raw/sources/my-article.md"
```

### Research a topic from the web

Requires PinchTab running on port 9867:

```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{"query": "latest advances in vector databases", "max_sources": 3}'
```

```json
{
  "query": "latest advances in vector databases",
  "sources_ingested": 3,
  "files_created": ["web_latest-advances_0_1714000000.md", "..."],
  "contradictions_found": 0
}
```

### List detected contradictions

```bash
curl http://localhost:8000/contradictions
```

```json
{
  "contradictions": [
    {
      "page": "wiki/concepts/rag.md",
      "claim_a": "RAG requires an external vector store.",
      "claim_b": "RAG can operate with BM25 alone.",
      "sources": "source-v1.md vs source-v2.md",
      "detected": "2026-04-22 10:00:00"
    }
  ]
}
```

### Check service health

```bash
curl http://localhost:8000/health
```

---

## Dashboard UI

Open <http://localhost:8000/> in your browser after starting the server.

The single-page dashboard (`dashboard/index.html`) provides:

- **Header bar** — app name, live status dot (green = index ready), and a "Rebuild Index" button
- **Chat panel** — conversation history with markdown rendering, source tags, contradiction warnings, and a web-research badge when live sources were used
- **Upload panel** — drag-and-drop `.md` / `.txt` / `.pdf` ingestion, plus an internet research input that calls `/research`
- **Contradictions panel** — scrollable list of all auto-detected factual conflicts, refreshed from `/contradictions`

No build step, no npm, no frameworks — pure HTML/CSS/JS with marked.js from CDN.

---

## CLI Tools

```bash
# Ingest a source file and rebuild the RAG index
python tools/ingest.py raw/sources/my-article.md

# Full-text search over wiki pages
python tools/query.py "what is retrieval augmented generation?"

# Lint the wiki for orphans, broken links, and stale pages
python tools/lint.py
```

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

---

## Using with Obsidian

1. Open the repo folder as an Obsidian vault
2. The `wiki/` folder contains all linked pages
3. Use Obsidian's **Graph View** to visualize the knowledge graph
4. Use **Obsidian Web Clipper** to quickly add web articles as raw sources
5. Use the **Dataview** plugin to query page frontmatter

**Recommended Obsidian settings:**
- Set "Attachment folder path" → `raw/assets/`
- Enable "Use `[[Wikilinks]]`" for cross-references

---

## Contributing

Contributions are welcome! Please follow these conventions:

- **Code style** — follow PEP 8; use type annotations throughout
- **Docstrings** — add a Google-style docstring to every new function and class
- **Modularity** — keep new features in their own module; update `app.py` only to wire in a new endpoint
- **Tests** — add or update tests when modifying `core/` or `tools/` logic
- **No new dependencies** unless strictly necessary; prefer the stdlib or packages already in `requirements.txt`
- **Markdown** — follow the page templates in `schema/AGENTS.md` when creating wiki content

To contribute:

```bash
# Fork the repo, then:
git checkout -b feature/my-improvement
# Make your changes
git commit -m "feat: describe your change"
git push origin feature/my-improvement
# Open a pull request
```

---

## Philosophy

- **Raw sources are immutable** — the LLM reads but never modifies them
- **The wiki is LLM-owned** — you read it, the LLM writes and maintains it
- **You curate, the LLM bookkeeps** — you add sources and ask questions; the LLM handles summaries, cross-references, and consistency
- **Local-first** — everything is plain markdown in git; no database, no cloud dependency
- **Progressive complexity** — start simple, extend as needed

Inspired by Vannevar Bush's *Memex* (1945) — a personal, curated knowledge store with associative trails.

---

## License

This project is released under the [MIT License](LICENSE).
