# Personal Knowledge Engine — System Architecture

Last updated: 2026-03-07 08:32 EST

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

Analysis of the Joplin corpus identified four note archetypes that
require different chunking approaches. The chunker must handle all four.

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

### Archetype D — Travel Journal
Characteristics: single note per multi-day trip (10+ pages), day
markers of varying formats, images interspersed inline, written
in real time during the trip.

Primary split: day marker detection — handles all observed formats:
    Day 1, Day 2, Day 2 Harry Goldens Trail   (explicit numbered)
    Sunday, Monday, Sat                        (standalone day names)
    Sunday we stopped over at...               (day name in prose)
    The second week...Monday rained.           (narrative transition)

Timestamp strategy — three tiers:
    Tier 1 (explicit): date found in chunk text e.g. Tuesday 9/8/15
        → store directly as entry_timestamp
    Tier 2 (calculated): day name or Day N marker found, no explicit date
        → calculate from note created_at + day offset
        → store as entry_timestamp with prefix "calculated: "
        → relies on notes being written in real time (confirmed pattern)
        → duplicate day names (two Sundays) resolved by sequence order
    Tier 3 (none): no day marker detectable
        → entry_timestamp left null
        → note-level created_at provides rough temporal signal

Image handling — three active formats:
    Markdown:  ![alt](:/resource_id)           → strip, store resource_id
    HTML:      <img src=":/resource_id" .../>   → strip, store resource_id
    Audio:     [filename.m4a](:/resource_id)    → strip, store resource_id

Broken placeholder handling — strip silently, no resource_id stored:
    {picture)    (Picture)    (picture)    image

Consecutive images with no text between them: kept together, all
resource_ids added to the surrounding chunk's resource_ids array.

Pre-trip planning block: treated as its own reference chunk, flagged
with note_type: travel in metadata. Checklist content preserved,
not stripped.

Fallback: paragraph boundaries where day detection fails.

Metadata flag: note_type: travel stored per chunk for post-hoc
retrieval quality analysis.

Resource IDs stored in chunks.resource_ids (TEXT[] column).

### Archetype E — Oral History / Conversation Notes
Characteristics: sparse text as outline or index, audio recordings
as primary content, photos of people or historical documents,
fragmentary sentences, single conversation per note.

Audio filename timestamps (e.g. 20150621 00:15:50) are the most
reliable timestamp signal in the entire corpus — precise to the
second, reliable because recordings are made in real time.

Chunking: embed whole note if below threshold. If above threshold,
chunk on audio file boundaries — each recording plus surrounding
text forms a semantic unit.

Timestamp: extracted from audio filename, stored as entry_timestamp
in format YYYY-MM-DD HH:MM:SS.

Resource handling:
- Audio (.m4a, .mp3): strip from text, store resource_id in
  resource_ids, flag as resource_type: audio in metadata
- Images: same handling as Archetype D

Future capability: Whisper API transcription of audio content.
Transcriptions stored as chunk text, making spoken content fully
retrievable. Original audio surfaced as playable media in the
Obsidian insight panel. See milestone 9.x Audio Transcription.
- Apply chunking selectively: notes above ~1000 characters only
- Below threshold: note embedding serves as chunk embedding
- Date stamp regex must tolerate typo variants (spaces, double slashes,
  2-digit and 4-digit years)
- Minimum chunk: ~100 tokens
- Maximum chunk: ~500 tokens with 1-2 sentence overlap at boundaries
- Chunking module: pke/chunking/chunker.py (milestone 8.9.6)

### Chunks Table Schema (current — as of milestone 8.9.5)

    CREATE TABLE chunks (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        note_id          UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
        chunk_index      INTEGER NOT NULL,
        chunk_text       TEXT NOT NULL,
        embedding        vector(1536),
        char_start       INTEGER NOT NULL,
        char_end         INTEGER NOT NULL,
        section_title    TEXT,
        entry_timestamp  TEXT,
        resource_ids     TEXT[] DEFAULT '{}',
        created_at       TIMESTAMPTZ DEFAULT now(),
        UNIQUE (note_id, chunk_index)
    );

entry_timestamp format:
    Explicit date:   "2015-09-08"
    Calculated date: "calculated: 2014-08-04"
    Not available:   NULL

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

Output — every result must include:
- note_id          for Obsidian deep link construction
- note_title       human-readable label
- notebook         for context and filtering
- matched_text     the relevant passage (raw, never summarized)
- similarity_score for ranking
- char_start       exact position in source note
- char_end         exact position in source note
- entry_timestamp  date of entry (explicit or calculated)
- resource_ids     associated images/audio resource IDs
- resource_types   type flags per resource (image, audio)

Design principle — the insight panel is never a dead end:
Every surfaced passage must link back to its full source context.
char_start and char_end enable the Obsidian plugin to navigate
to the exact paragraph within the note, not just the note title.
Audio chunks link to playable recordings. Image chunks link to
the note at the position of the photo.

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

**The insight panel is never a dead end.**
Every surfaced passage links back to its full source context:
- Click note title → opens the source note in Obsidian
- Click passage → opens source note at the exact paragraph
  (using char_start offset for precise navigation)
- Audio chunks → inline play button for the original recording
- Image chunks → opens note at the photo location

The panel is ambient, not intrusive. The user controls their
own thinking. The system provides material, not conclusions.

### Note Conventions (Dimension 2)

Future notes follow light conventions by type to improve chunking
precision. See ROADMAP.md for full convention definitions.

---

## 15. Multi-Source Architecture (Planned)

Each content source gets its own parser. All parsers produce the same
ParsedNote contract. The ingestion pipeline is source-agnostic.

### Parser Reusability Principle
The Joplin sync-folder parser is not legacy code — it is the first
implementation of a pluggable parser pattern that will support many
sources. It remains a maintained, reusable parser valuable to any
Joplin user building a similar system. The pattern:

    Source files → Parser → ParsedNote contract → Ingest pipeline

is identical for every future parser. Only the parser changes.

### Plain Text Is Always the Source of Truth
The database is an index, never an archive. Re-ingestion from source
files is always possible and always safe. The database should never
be treated as the source of truth for content reconstruction.

### Migration Strategy (Joplin → Obsidian)
See ROADMAP.md milestone 9.x — Obsidian Parser + Migration for the
full four-phase migration plan including validation gate.

### Planned Parsers
- pke/parsers/obsidian_parser.py (primary writing surface migration)
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
