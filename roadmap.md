# Personal Knowledge Engine — Product Roadmap

This document captures the strategic vision, milestone sequence, and
per-milestone design notes for the PKE project. It is persistent across
sessions and should be updated whenever direction changes.

ARCHITECTURE.md is the structural truth.
CURRENT_TASK.md is the tactical truth.
This document is the directional truth.

---

## Vision

A personal intelligence layer that ingests content from multiple channels —
notes, messages, email, and others — embeds and indexes that content
semantically, and surfaces relevant insights during the act of writing itself.

The system has two faces:

**The pipeline** — a deterministic, reproducible ingestion system that keeps
the knowledge base current. Pluggable parsers per content channel. Clean
contracts between parse and ingest stages. No vendor lock-in.

**The writing environment** — an Obsidian-based writing surface with a
custom plugin that queries the PKE retrieval API in real time as the user
writes, surfacing semantically relevant chunks from personal history in a
live insight panel alongside the writing surface.

The long-term experience: writing a journal entry and seeing, in a sidebar,
the most relevant passages from years of prior entries — not because you
searched for them, but because the system recognized the connection.

---

## Core Design Principles

These must survive as the system grows:

- Deterministic, reproducible ingestion
- Pluggable parsers per content channel
- Clean contract between parse and ingest stages
- Retrieval precision that scales with content length and complexity
- The writing process belongs to the user — the system serves it, never
  replaces it
- No vendor lock-in at any layer (parser, embedding, storage, writing surface)
- Plain-text, user-owned notes as the source of truth

---

## Writing Environment Decision

**Chosen platform: Obsidian**

Obsidian replaces Joplin as the primary writing surface. Key reasons:

- Local-first, plain Markdown files — user owns all content always
- Strong plugin API enables custom insight panel without full custom build
- Good writing experience, flexible structure, light templating support
- Full-text search, tagging, backlinking, graph view all built in
- Low longevity risk — files survive even if Obsidian disappears
- Eliminates Evernote-style lock-in risk permanently

**What was rejected and why:**

- Joplin: too rigid, poor writing experience, limited integration surface
- Evernote: declining product, historically poor file access, lock-in risk
- Notion: heavy, possible but not ideal for real-time plugin integration
- Custom web app: right long-term destination if Obsidian proves
  insufficient, but premature before the insight panel has been lived
  with in any form
- Bear / Craft / Capacities: insufficient integration capability or
  longevity risk

**The Obsidian insight plugin** will watch the active note, send the
current paragraph or entry to the PKE retrieval API after a short
debounce, and render the top 3-5 semantically similar chunks from
personal history in a side panel. The panel shows date, note title,
and the relevant passage — raw content, not AI-generated summaries.
The user draws their own conclusions.

---

## Note Corpus Philosophy

### Dimension 1 — Historical Notes (Joplin corpus)

The existing Joplin corpus must be treated as best-effort extraction
from imperfect source material. Notes were written for the moment, not
for a retrieval system. The chunker must be tolerant and adaptive.

Before chunking is implemented (8.9.6), a targeted re-read and light
restructuring of the most important notes is recommended. This is not
just data cleanup — it is the first act of insight generation. Themes
will emerge during re-reading that will inform what the retrieval
system needs to find well.

Restructuring conventions for historical notes:
- Add a ## Current State section at the top of reference notes
  (medical log, medication lists, ongoing project notes)
- Normalize date formats where possible
- Add blank lines between entries in long running notes
- Add retrospective annotations where memory is fresh — these are
  semantically rich content, not just metadata

### Dimension 2 — Future Notes (Obsidian)

New notes should follow light conventions by type. Not rigid templates
— invitations to structure. The goal is enough consistency that the
chunker can be precise without making note-taking feel like data entry.

Journal entries:
    ## YYYY-MM-DD
    [free writing]

Medical / reference logs:
    ## Current State
    [current medications, current status — updated in place]
    ---
    ## Log
    ### YYYY-MM-DD
    [dated entries appended below]

Book / idea notes:
    ## Summary
    [2-3 sentence synthesis]
    ## Notes
    [free capture]

These conventions are suggestions, not enforcement. The system adapts
to the content. But notes written with these conventions will produce
significantly better retrieval quality.

---

## Note Archetypes Identified

Analysis of the Joplin corpus revealed three distinct archetypes
that the chunker must handle:

**Archetype A — Fragmented journal**
- Short, fragmented entries, 1-10 lines each
- High noise ratio (URLs, codes, one-liners)
- Date stamps are the only consistent structure
- Chunking: split on date stamps, merge entries under ~100 tokens
  with neighbors

**Archetype B — Structured journal**
- Long entries, 200-500 words each
- Consistent internal template (Score, What did I do well, etc.)
- Date stamps as primary boundary, template sections as secondary
- Retrospective annotations embedded inline — must be preserved
- Chunking: split on date stamps, use template section headers
  as secondary boundaries for long entries

**Archetype C — Reference / medical log**
- Mixed structure: undated header (current state) + dated log
  + embedded sub-tables (e.g. injection schedule)
- Undated header section is most retrieval-valuable
- Sub-tables should be kept intact, not split on internal dates
- Chunking: treat undated opening section as its own chunk,
  split dated log on date stamps, preserve embedded sub-tables

---

## Content Channels (Current and Planned)

| Channel          | Status      | Notes                                       |
|------------------|-------------|---------------------------------------------|
| Joplin notes     | ✅ Complete  | Sync-folder parser, canonical Stage 1       |
| Obsidian notes   | 🔵 Planned  | Future primary writing surface              |
| iMessage threads | 🔵 Planned  | Specific contacts or groups                 |
| Yahoo Mail       | 🔵 Planned  | Select senders                              |
| Others (TBD)     | 🔵 Open     | Calendar, bookmarks, documents              |

### Obsidian
- Source: local vault Markdown files
- Parser follows same sync-folder parser pattern
- Consistent date format conventions from day one
- Ingest on save or on scheduled basis (TBD)
- Frontmatter and inline tags both supported

### iMessage
- Source: ~/Library/Messages/chat.db (SQLite, read-only)
- Scope: specific contacts or group threads, not full history
- Key challenges: contact scoping, group attribution,
  media/attachments, deduplication with notes
- ParsedNote contract extension: deferred

### Yahoo Mail
- Source: IMAP live connection or exported MBOX (TBD)
- Scope: select senders, possibly select folders
- Key challenges: threading model, HTML body stripping, attachments
- ParsedNote contract extension: deferred

---

## Milestone Sequence

---

### ✅ 8.9.4 — Deterministic Ingestion Baseline
**Status: COMPLETE (2026-03-03)**

Clean deterministic baseline in Supabase. Fixed parse_cli.py to wire
canonical sync-folder parser. Fixed dry-run mode. Validated idempotency.

Result: 1489 notes, 16 notebooks, 57 tags, 212 relationships.

---

### 🔄 8.9.5 — Real Embeddings + Chunk Schema Foundation
**Status: IN PROGRESS**

Replace placeholder embeddings with real OpenAI embeddings. Add empty
chunks table to Supabase as schema foundation for 8.9.6.

Key decisions:
- Provider: OpenAI text-embedding-3-small (1536 dimensions)
- New EmbeddingClient: pke/embedding/openai_client.py
- Re-ingest all 1489 notes in place (idempotent upsert)
- chunks table created via migration script; not populated
- chunks table schema includes section_title and entry_timestamp
  fields in anticipation of 8.9.6
- Embedding failures non-fatal; tracked in IngestionReport

---

### 🔵 8.9.6 — Chunking for Long Notes
**Status: PLANNED**

Archetype-aware chunking for notes above a length threshold.
Populate the chunks table. Handle all three archetypes correctly.

Key decisions:
- Primary split: date stamps (regex tolerates typo variants)
- Secondary split: template section headers (Archetype B)
- Undated opening sections treated as reference chunks (Archetype C)
- Embedded sub-tables kept intact
- Minimum chunk: ~100 tokens; merge short entries with neighbors
- Maximum chunk: ~500 tokens; split on paragraph boundaries
  with 1-2 sentence overlap
- Chunking module: pke/chunking/chunker.py
- Applied selectively: notes above ~1000 characters only

Pre-work recommended before implementation:
- Re-read and lightly restructure 10-15 most important notes
- Add Current State headers to reference notes
- Normalize date formats in key journal notes
- These notes become primary test cases for the chunker

---

### 🔵 8.9.7 — Retrieval API
**Status: PLANNED**

FastAPI retrieval endpoint. The engine that powers both search and
the Obsidian insight panel.

Key decisions:
- Endpoint: POST /query
- Input: query text, optional filters (notebook, date range, source)
- Returns: ranked chunks with note title, notebook, date, matched
  text, similarity score, char offsets, surrounding context
- Hybrid retrieval: chunk-level where chunks exist, whole-note fallback
- Response format designed for insight panel: enough context to render
  a meaningful passage, not just a similarity score
- Supabase vector search via pgvector

---

### 🔵 8.9.8 — Obsidian Insight Plugin
**Status: PLANNED**

The Obsidian plugin that connects the writing surface to the PKE
retrieval API. The primary consumer-facing expression of the system.

Key decisions:
- Plugin watches active note
- After short debounce, sends current paragraph to POST /query
- Renders top 3-5 results in a side panel
- Each result: date, note title, relevant passage (raw text)
- No AI-generated summaries — raw content only, user draws conclusions
- Results optionally appendable to current entry as dated annotation
- Built with Obsidian plugin API (TypeScript)
- Requires PKE retrieval API (8.9.7) running locally or hosted

Writing surface setup (same milestone):
- Obsidian vault configured as primary writing tool
- Light templates by note type installed
- Journal, medical/reference, book/idea templates defined
- Migration plan for Joplin notes into Obsidian vault

---

### 🔵 8.9.9 — Insight Generation
**Status: PLANNED — design TBD**

Higher-order insight generation on top of the retrieval layer.
Design should emerge from experience with the Obsidian plugin.

Possible directions:
- Temporal synthesis: "what did I think about X over time?"
- Corpus summarization: "what patterns emerge in this notebook?"
- Relationship surfacing: "what connects these two notes?"
- Conversational Q&A over the full knowledge base
- Morning briefing: auto-generated digest from recent notes
  and patterns tailored to current priorities

Notes:
- Requires generation layer on top of retrieval
- Quality of chunking (8.9.6) directly determines insight quality
- The insight panel (8.9.8) is the natural delivery surface

---

### 🔵 9.x — Obsidian Parser
**Status: PLANNED**

Add Obsidian vault as ingestion source alongside Joplin.
Eventually becomes primary source as writing migrates.

Key decisions:
- New parser: pke/parsers/obsidian_parser.py
- Source: local Obsidian vault directory (Markdown files)
- Frontmatter support: YAML frontmatter natively supported
- Tags extracted from both inline (#tag) and frontmatter
- Backlinks extractable as relationships
- ParsedNote contract unchanged

---

### 🔵 9.x — iMessage Parser
**Status: FUTURE**

Add iMessage as ingestion source. Specific contacts or group threads
from the macOS Messages SQLite database.

---

### 🔵 9.x — Yahoo Mail Parser
**Status: FUTURE**

Add Yahoo Mail as ingestion source. Select senders or folders.
Source format (IMAP vs MBOX) TBD.

---

## Future Concepts (Conceptual Horizon)

Named now so no near-term decision closes them off accidentally.

**Insight Listener**
Real-time monitoring of new notes to surface relevant insights as
content is created. The Obsidian plugin is the first expression.
Implies eventual move toward real-time or near-real-time ingestion.

**Cross-Source Timeline Intelligence**
Unified queryable timeline across notes, email, messages, calendar.
Requires reliable normalized timestamps across all sources — a
constraint to design into parsers early, not retrofit later.

**Relationship Intelligence**
Track people and shared context across sources. Surface relationship
graphs and interaction summaries. Names like Killian, Ger, Dad appear
across hundreds of entries — high-value retrieval territory.
Requires consistent person entity extraction across all parsers.

**Context-Aware Prompting**
Dynamic prompting based on current focus, recent notes, recurring
patterns. The writing environment knowing "this topic comes up every
time you mention this person." Consumer-facing expression of
everything being built.

**Morning Briefing Generator**
Auto-generated daily digest from recent notes, tasks, and patterns.
Natural output of the insight generation layer (8.9.9).

**Agentic Automation Layer**
Trigger workflows based on note content, tags, or semantic patterns.
Powerful but carries risk of conflicting with determinism and clean
contracts principles. Tension worth naming explicitly when designed.

---

## Cross-Cutting Concerns (Deferred)

**Identity and deduplication across sources**
If a topic appears in a note and an iMessage thread, how does the
system know they are related? Deferred until multi-source is real.

**ParsedNote contract extension**
Adding source_type would allow filtering by source. Deferred to
first multi-source parser milestone.

**Ingestion versioning**
Should Supabase store an ingestion version marker per note?
Raised in 8.9.4, still open.

**Scheduled ingestion**
Currently manual. Relevant once Obsidian writing is continuous.

**Retry and resilience**
Exponential backoff for transient API failures. Deferred post-MVP.

**Obsidian sync strategy**
Obsidian paid sync vs iCloud vs git-based sync. Decision needed
before Obsidian becomes primary writing tool. Affects where the
vault lives and how the parser accesses it.