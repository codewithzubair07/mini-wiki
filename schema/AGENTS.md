# AGENTS.md — LLM Wiki Operating Instructions

This file defines how the LLM agent should operate on this wiki.
Read this file at the start of every session before making any changes.

---

## Repository Layout

```
raw/sources/      ← immutable source documents. Never modify.
raw/assets/       ← images and attachments. Never modify.
wiki/index.md     ← master catalog of all wiki pages. Always keep up to date.
wiki/log.md       ← append-only operation log. Always append, never edit existing entries.
wiki/entities/    ← one page per entity (person, company, project, book, …)
wiki/concepts/    ← one page per concept, idea, or theme
wiki/sources/     ← one summary page per ingested source
wiki/syntheses/   ← comparisons, analyses, overviews you or the user request
schema/           ← this file and other agent instructions
tools/            ← helper scripts
```

---

## Core Rules

1. **Raw sources are immutable.** Read them; never edit or delete them.
2. **Prefer updating existing pages over creating new ones.** Before creating a page, check whether a closely related one already exists.
3. **Always update `wiki/index.md`** after creating or significantly updating any wiki page.
4. **Always append to `wiki/log.md`** after every ingest, query session, or lint pass.
5. **Backlink discipline.** When you mention a wiki page in another page, use `[[Page Name]]` wikilink syntax and make sure the target page also references the source page where it makes sense.
6. **Flag contradictions; don't silently overwrite.** If new information contradicts existing content, add a `## Contradictions / Open Questions` section and note both claims with their sources.
7. **Keep pages concise.** Summaries should be 2–4 sentences. Expand only when the content genuinely warrants it.
8. **Use YAML frontmatter** on every wiki page (see template below).
9. **Never invent sources.** Only cite documents that actually exist in `raw/sources/`.

---

## Page Frontmatter Template

```yaml
---
title: "Page Title"
type: entity | concept | source | synthesis
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [source-slug-1, source-slug-2]
---
```

---

## Ingest Workflow

When the user asks you to ingest a source file:

1. **Read** the source file from `raw/sources/`.
2. **Discuss** key takeaways with the user if they are present (optional but preferred).
3. **Create** a source summary page in `wiki/sources/<slug>.md` using the Source Page Template.
4. **Identify** entities and concepts mentioned in the source.
5. **Update** each relevant entity page in `wiki/entities/`. Create pages that don't exist yet.
6. **Update** each relevant concept page in `wiki/concepts/`. Create pages that don't exist yet.
7. **Update** `wiki/index.md` — add the new source page and any new entity/concept pages.
8. **Append** an entry to `wiki/log.md` in the format:
   ```
   ## [YYYY-MM-DD] ingest | <Source Title>
   - Pages created: …
   - Pages updated: …
   - Entities: …
   - Concepts: …
   ```
9. Summarize what you did in your reply to the user.

A single source may update 5–15 wiki pages. That is expected and correct.

---

## Query Workflow

When the user asks a question:

1. **Read** `wiki/index.md` to find relevant pages.
2. **Read** those pages.
3. **Synthesize** an answer with citations to wiki pages (use `[[Page Name]]` links).
4. **Offer** to save the answer as a synthesis page in `wiki/syntheses/` if it is substantive.
5. If you do save it, update `wiki/index.md` and append to `wiki/log.md`.

---

## Lint Workflow

When the user asks you to lint or health-check the wiki:

1. Scan all files in `wiki/` (excluding `index.md` and `log.md`).
2. Report:
   - **Orphan pages** — pages with no inbound `[[wikilinks]]` from other wiki pages.
   - **Broken links** — `[[wikilinks]]` that reference pages that do not exist.
   - **Empty pages** — pages with no content beyond the frontmatter.
   - **Duplicate candidates** — pages with very similar titles that might be the same topic.
   - **Stale claims** — sections explicitly marked `<!-- stale -->` or containing dates that appear outdated.
3. Offer to fix each category of issue.
4. Append a lint report entry to `wiki/log.md`.

---

## Page Templates

### Entity Page (`wiki/entities/<slug>.md`)

```markdown
---
title: "Entity Name"
type: entity
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: []
---

# Entity Name

## Summary
One to three sentences describing what this entity is.

## Key Facts
- Fact one
- Fact two

## Connections
- Related to [[Concept Name]]
- Related to [[Other Entity]]

## Contradictions / Open Questions
_None yet._

## Sources
- [[source-slug]]
```

### Concept Page (`wiki/concepts/<slug>.md`)

```markdown
---
title: "Concept Name"
type: concept
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: []
---

# Concept Name

## Summary
One to three sentences defining the concept.

## Why It Matters
Brief explanation of why this concept is significant in the context of this wiki.

## Key Claims
- Claim one (source: [[source-slug]])
- Claim two

## Contradictions / Open Questions
_None yet._

## Related Pages
- [[Related Concept]]
- [[Related Entity]]

## Sources
- [[source-slug]]
```

### Source Page (`wiki/sources/<slug>.md`)

```markdown
---
title: "Source Title"
type: source
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
original_file: raw/sources/filename.md
---

# Source: Source Title

## Summary
2–4 sentence summary of the source.

## Key Claims
- Claim one
- Claim two
- Claim three

## Extracted Entities
- [[Entity Name]]

## Extracted Concepts
- [[Concept Name]]

## Notes
Any caveats, context, or quality notes about this source.
```

### Synthesis Page (`wiki/syntheses/<slug>.md`)

```markdown
---
title: "Synthesis Title"
type: synthesis
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: []
---

# Synthesis Title

## Overview
Brief description of what this synthesis covers.

## Key Findings
- Finding one
- Finding two

## Comparison / Analysis
_Main content here._

## Open Questions
- Question one

## Related Pages
- [[Related Page]]

## Sources
- [[source-slug]]
```

---

## index.md Structure

`wiki/index.md` should be organized as follows and updated after every ingest:

```markdown
# Wiki Index

_Last updated: YYYY-MM-DD — N pages total_

## Sources
| Page | Summary | Date |
|------|---------|------|
| [[source-slug]] | One-line summary | YYYY-MM-DD |

## Entities
| Page | Summary |
|------|---------|
| [[entity-slug]] | One-line summary |

## Concepts
| Page | Summary |
|------|---------|
| [[concept-slug]] | One-line summary |

## Syntheses
| Page | Summary |
|------|---------|
| [[synthesis-slug]] | One-line summary |
```

---

## log.md Entry Format

Each entry must start with this header pattern so it is grep-parseable:

```
## [YYYY-MM-DD] <operation> | <title>
```

Where `<operation>` is one of: `ingest`, `query`, `lint`, `update`, `synthesis`.

Example:
```
## [2026-04-20] ingest | LLM Wiki Pattern Article
- Pages created: wiki/sources/llm-wiki-pattern.md, wiki/concepts/retrieval-augmented-generation.md
- Pages updated: wiki/index.md, wiki/log.md
- Entities: none
- Concepts: LLM Wiki, RAG
```

---

## Naming Conventions

- File names: lowercase, hyphen-separated, no spaces. Example: `andrej-karpathy.md`
- Page titles: Title Case. Example: `Andrej Karpathy`
- Wikilinks: use the page title exactly as it appears in the `title` frontmatter field
- Avoid special characters in file names

---

## What To Do When Unsure

- When a new concept or entity could go in either category, prefer `concepts/` for abstract ideas and `entities/` for concrete named things (people, organizations, products, books).
- When a source contains a lot of dense information, create the source page and stub out entity/concept pages; you can expand them on the next ingest or at the user's request.
- When content is ambiguous or contradictory, always flag it rather than guessing.
