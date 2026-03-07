# Personal Knowledge Engine — System Architecture

This document defines the architecture, contracts, and sequencing of the
Personal Knowledge Engine (PKE). It is the authoritative reference for all
system-level reasoning, design decisions, and future development. All AI
tools must treat this document as the source of truth.

---

## 1. System Overview

The Personal Knowledge Engine is a personal intelligence layer with two
faces:

**The pipeline** — a deterministic, two-stage ingestion system that converts
personal notes into a structured, queryable knowledge base backed by
Supabase and embeddings.

**The writing environment** — an Obsidian-based writing surface with a
custom plugin that queries the PKE retrieval API in real time, surfacing
semantically relevant chunks from personal history in a live insight panel
as the user writes.

The canonical pipeline workflow is:

    pke parse run
    pke ingest run --dry-run
    pke ingest run

The system is built around:
- Deterministic, reproducible ingestion
- Explicit contracts between stages
- Pluggable parsers per content source
- Dependency-injected clients
- Testability and isolation
- Clean separation of concerns
- User ownership of all content (plain text, no lock-in)

---

## 2. Pipeline Architecture

### Stage 1 — Parse

Goal: Convert raw note sources into a structured, lossless JSON artifact.

Entry point:   pke/cli/parse_cli.py
Parser:        pke/parsers/joplin_sync_parser.py  ← canonical, must not change
Output file:   pke/artifacts/parsed/parsed_notes.json

This file is the only input to Stage 2.

IMPORTANT: parse_cli.py must import from joplin_sync_parser, not
joplin_markdown. The Markdown export parser is deprecated and must
never be wired into the CLI.

### Stage 2 — Ingest

Goal: Transform parsed notes into Supabase entities with embeddings,
tags, notebooks, relationships, and chunks.

Entry point:   pke/cli/ingest.py
Orchestrator:  pke/ingestion/orchestrator.py

Steps:
- Extract and upsert notebooks
- Extract and upsert tags
- Upsert notes with embeddings
- Link notes ↔ tags
- Chunk notes above length threshold (milestone 8.9.6+)

The orchestrator is deterministic and idempotent.

---

## 3. Parser History and Current State

### Markdown Export Parser (Deprecated)

The original parser targeted Joplin's Markdown export format. This
approach failed because Joplin produced incomplete exports. This parser
(joplin_markdown.py) remains in the repo for reference but must never
be modified or referenced in active code paths.

### Sync Folder Parser (Canonical Source)

File: pke/parsers/joplin_sync_parser.py

The Joplin sync folder is the correct and only source of truth for the
Joplin corpus. parse_cli.py is wired to this parser. Any future changes
to Stage 1 must go through joplin_sync_parser.py.

---

## 4. ParsedNote Contract

Every parsed note must contain exactly these fields:

```
{
    "id":             str,
    "title":          str,
    "body":           str,
    "notebook":       str,        # resolved notebook name or ""
    "tags":           list[str],  # resolved tag names
    "created_at":     str,        # ISO timestamp or ""
    "updated_at":     str,        # ISO timestamp or ""
    "metadata":       dict,       # all remaining metadata fields
    "source_file":    str,        # absolute path
    "resource_links": list[str],  # extracted resource IDs
}
```

Rules:
- No missing fields
- No extra fields
- No None values
- Empty string or empty list for missing metadata

This contract must not change without a formal design decision.
Extension for multi-source (source_type field) deferred to first
multi-source parser milestone.

---

## 5. Joplin Sync Folder Format

All data lives in .md files.

Type Map:
- type_ 1 → Note
- type_ 2 → Notebook
- type_ 5 → Tag
- type_ 6 → Note-tag relationship

---

## 6. Three-Pass Parser Architecture

Pass 1 — Load and Classify
Pass 2 — Build Lookup Maps (notebook_map, tag_map, note_tag_map)
Pass 3 — Enrich and Normalize Notes (resolve IDs, sort by id)

---

## 7. Determinism Requirements

- Running the parser twice on the same folder must produce identical output
- Notes must be sorted by id
- No shared mutable state across passes
- Running ingestion twice must produce identical Supabase state

---

## 8. Missing Metadata Rules

- Missing notebook → ""
- Missing tags → []
- Missing timestamps → ""
- Empty body → "" (parser preserves; orchestrator skips at ingest)
- Encrypted notes (encryption_applied: 1) → skip with warning

---

## 9. Parser vs Orchestrator — Intentional Contract Divergence

Parser (Stage 1): lossless — preserves all notes including empty-body
Orchestrator (Stage 2): meaningful — skips empty-body notes at ingest

Reason: empty-body notes produce no embedding and no search utility.
This divergence is intentional and must not change.

---

## 10. Note Archetypes and Chunking Strategy

Analysis of the Joplin corpus identified three note archetypes that
require different chunking approaches. The chunker must handle all three.

### Archetype A — Fragmented Journal
Characteristics: short entries (1-10 lines), high noise, date stamps
as only structure.
Chunking: split on date stamps, merge entries under ~100 tokens with
neighbors.

### Archetype B — Structured Journal
Characteristics: long entries (200-500 words), consistent internal
template (Score, What did I do well, etc.), retrospective annotations.
Chunking: split on date stamps (primary), template section headers
(secondary for long entries). Preserve retrospective annotations
with the entry they annotate.

### Archetype C — Reference / Medical Log
Characteristics: undated header (current state) + dated log +
embedded sub-tables.
Chunking: undated opening section as its own reference chunk, dated
log split on date stamps, embedded sub-tables kept intact.

### General Chunking Rules
- Apply chunking selectively: notes above ~1000 characters only
- Below threshold: note embedding serves as chunk embedding
- Date stamp regex must tolerate typo variants (spaces, double slashes,
  2-digit and 4-digit years)
- Minimum chunk: ~100 tokens
- Maximum chunk: ~500 tokens with 1-2 sentence overlap at boundaries
- Chunking module: pke/chunking/chunker.py (milestone 8.9.6)

---

## 11. Embedding Architecture

Provider: OpenAI text-embedding-3-small
Dimensions: 1536
Token limit: 8191 (truncate with warning if exceeded)
Client: pke/embedding/openai_client.py (implements EmbeddingClient protocol)
API key: OPENAI_API_KEY in .env (never committed)

Two embedding levels:
- Note-level embedding: whole-note embedding stored in notes table
- Chunk-level embedding: per-chunk embedding stored in chunks table
  (milestone 8.9.6+)

Retrieval uses chunk-level embeddings where available, note-level
as fallback (hybrid strategy, milestone 8.9.7).

---

## 12. Supabase Integration

Tables:
- notebooks
- tags
- notes (with embeddings)
- note_tags (relationships)
- chunks (with embeddings, added milestone 8.9.5)

Ingestion table reset order (when full reset required):

    TRUNCATE TABLE note_tags, conflicts, resources, chunks, notes, notebooks, tags;

Tables never truncated by the ingestion pipeline:
- ingestion_log
- documents
- deleted_notes

All DB operations go through SupabaseClient which supports real client,
DummyClient for dry-run, and mock clients for tests.

The parser must never call Supabase.

---

## 13. Retrieval API

Entry point: FastAPI application
Endpoint: POST /query

Input: query text, optional filters (notebook, date range, source)
Output: ranked chunks with note title, notebook, date, matched text,
similarity score, char offsets, surrounding context

Designed to serve both:
- Direct search queries
- Real-time insight panel requests from the Obsidian plugin

Hybrid retrieval: chunk-level where chunks exist, whole-note fallback.
Vector search via pgvector in Supabase.

---

## 14. Writing Environment Architecture

### Platform: Obsidian

Obsidian is the chosen writing surface, replacing Joplin.
Local-first, plain Markdown files, strong plugin API.

### Obsidian Insight Plugin

A custom Obsidian plugin (TypeScript) that:
1. Watches the active note for changes
2. After a short debounce, sends the current paragraph to POST /query
3. Renders the top 3-5 results in a side panel
4. Displays: date, note title, relevant passage (raw text)
5. Never generates AI summaries — surfaces raw content only

The insight panel is ambient, not intrusive. The user controls their
own thinking. The system provides material, not conclusions.

### Note Conventions (Dimension 2)

Future notes follow light conventions by type to improve chunking
precision. See ROADMAP.md for full convention definitions.

---

## 15. Multi-Source Architecture (Planned)

Each content source gets its own parser. All parsers produce the same
ParsedNote contract. The ingestion pipeline is source-agnostic.

Planned parsers:
- pke/parsers/obsidian_parser.py (next after current Joplin corpus)
- pke/parsers/imessage_parser.py (iMessage threads)
- pke/parsers/yahoo_mail_parser.py (email from select senders)

ParsedNote contract extension (source_type field) deferred to first
multi-source milestone.

---

## 16. Testing Philosophy

- Deterministic ingestion
- Dependency injection
- No network calls in unit tests
- Fixtures for parsed notes
- E2E tests for parse → ingest

Test files:
- tests/test_joplin_sync_parser.py
- tests/test_openai_embedding_client.py (milestone 8.9.5)
- tests/test_chunker.py (milestone 8.9.6)

---

## 17. Collaboration Workflow

Development follows a three-step loop:
- Design (Thomas + Claude)
- Implement (VS Code Copilot)
- Review (Thomas + Claude)

All decisions are recorded in CURRENT_TASK.md.
ARCHITECTURE.md is the authoritative reference and must be updated
whenever a structural decision changes.
ROADMAP.md captures strategic direction and must be updated when
vision or milestone sequencing changes.