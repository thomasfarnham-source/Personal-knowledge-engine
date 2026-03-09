# Personal Knowledge Engine — System Architecture

Last updated: 2026-03-08 21:48 EST

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

Analysis of the Joplin corpus identified five note archetypes that
require different chunking approaches. The chunker handles all five.

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

### Chunking Module Structure (milestone 8.9.6)

    pke/chunking/
        __init__.py
        chunk.py              — Chunk dataclass (extracted to avoid circular imports)
        chunker.py            — public API: chunk_note(), detect_archetype()
        date_parser.py        — parse_date(), is_date_header(), is_ambiguous_date()
        resource_extractor.py — extract_resources(), ResourceResult
        archetype_a.py        — chunk_archetype_a() — implemented
        archetype_b.py        — chunk_archetype_b() — implemented
        archetype_c.py        — chunk_archetype_c() — implemented
        archetype_d.py        — chunk_archetype_d() — implemented
        archetype_e.py        — chunk_archetype_e() — implemented

Chunking rules:
- Apply selectively: notes above ~1000 characters only
- Below threshold: note embedding serves as chunk embedding
- Minimum chunk: ~100 tokens — merge short entries with neighbors
- Maximum chunk: ~500 tokens — split on section boundaries
- Date stamp regex must tolerate typo variants (spaces, double slashes,
  2-digit and 4-digit years)
- Chunker wired into orchestrator: runs after each note upsert
- Re-ingest strategy: delete_chunks_for_note() then upsert_chunks()
  (safe because database is an index, never an archive)

### Chunks Table Schema (current — as of milestone 8.9.6)

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
Token limit: 8191 (truncated using tiktoken before sending)
Client: pke/embedding/openai_client.py (implements EmbeddingClient protocol)
API key: OPENAI_API_KEY in .env (never committed)
Tokenizer: tiktoken — used for accurate token counting and truncation
    Character-based truncation is unreliable for this corpus due to
    markdown, special characters, and Irish/non-English text.
    tiktoken is a formal project dependency (pyproject.toml).

Two embedding levels:
- Note-level embedding: whole-note body truncated to 8191 tokens,
  stored in notes table. For very long notes this is a fallback only —
  these notes are always retrieved via chunk embeddings.
- Chunk-level embedding: per-chunk embedding stored in chunks table.
  Generated by pke/cli/embed_chunks.py backfill CLI.

Retrieval uses chunk-level embeddings where available, note-level
as fallback (hybrid strategy — see Section 13).

Corpus state as of milestone 8.9.7:
- 1489 notes with real OpenAI embeddings, 0 failures
- 866 chunks with real OpenAI embeddings

---

## 12. Supabase Integration

Tables:
- notebooks
- tags
- notes (with embeddings)
- note_tags (relationships)
- chunks (with embeddings, populated milestone 8.9.7)

SQL migration scripts:
- scripts/add_chunks_table.sql — chunks table schema
- scripts/add_match_functions.sql — match_chunks and match_notes
  pgvector RPC functions

Ingestion table reset order (when full reset required):

    TRUNCATE TABLE note_tags, conflicts, resources, chunks, notes, notebooks, tags;

Tables never truncated by the ingestion pipeline:
- ingestion_log
- documents
- deleted_notes

All DB operations go through SupabaseClient which supports real client,
DummyClient for dry-run, and mock clients for tests.

The parser must never call Supabase.

SupabaseClient methods added in milestone 8.9.7:
- fetch_unembedded_chunks(batch_size) — chunks WHERE embedding IS NULL
- update_chunk_embedding(chunk_id, embedding) — writes embedding to chunk
- match_chunks(query_embedding, match_count, filter_notebook) — pgvector RPC
- match_notes(query_embedding, match_count, filter_notebook) — pgvector RPC
  fallback (NOT EXISTS subquery ensures no overlap with chunk results)

---

## 13. Retrieval API (milestone 8.9.7 — COMPLETE)

Entry point: pke/api/main.py — FastAPI application
Endpoint: POST /query

File structure:
    pke/
        api/
            __init__.py
            main.py              — FastAPI app, dependency wiring at startup
            routes/
                __init__.py
                query.py         — POST /query endpoint
            models/
                __init__.py
                query.py         — QueryRequest, QueryResult, QueryResponse
        retrieval/
            __init__.py
            retriever.py         — Retriever class, hybrid retrieval logic
        cli/
            embed_chunks.py      — backfill chunk embeddings CLI

Input:
```json
{
    "query":     "string",
    "notebook":  "string (optional)",
    "date_from": "YYYY-MM-DD (optional)",
    "date_to":   "YYYY-MM-DD (optional)",
    "limit":     "int (optional, default 5, max 20)"
}
```

Output — per result:
```json
{
    "note_id":          "UUID — for Obsidian deep link construction",
    "note_title":       "string — human-readable label",
    "notebook":         "string — for context and filtering",
    "matched_text":     "string — relevant passage (raw, never summarized)",
    "similarity_score": "float — cosine similarity for ranking",
    "chunk_index":      "int — position within note",
    "section_title":    "string or null",
    "entry_timestamp":  "string or null — explicit or calculated date",
    "resource_ids":     "list[str] — associated image/audio resource IDs",
    "result_type":      "chunk or note"
}
```

Hybrid retrieval strategy:
1. Embed query text via OpenAI text-embedding-3-small
2. Search chunks table via match_chunks RPC (pgvector cosine distance)
3. Search notes table via match_notes RPC (fallback — NOT EXISTS subquery
   prevents overlap with chunk results)
4. Merge results, rank by similarity score descending
5. Return top N QueryResult objects

Scoring hook: Retriever._score() returns raw cosine similarity.
Isolated for future extension: recency decay, archetype weighting,
timestamp confidence signals.

Design principle — the insight panel is never a dead end:
Every surfaced passage carries enough information for the Obsidian
plugin to link back to the exact location in the source note.
Audio chunks link to playable recordings. Image chunks link to
the note at the position of the photo.

Deep link infrastructure:
- note_id → Obsidian URI or Joplin x-callback-url
- chunk_index + char_start → exact paragraph navigation
- resource_ids → image thumbnails or audio play buttons

To start the API server:
    uvicorn pke.api.main:app --reload

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
- pke/parsers/handwritten_journal_parser.py (Moleskine digitization)

ParsedNote contract extension (source_type field) deferred to first
multi-source milestone.

---

## 16. Testing Philosophy

- Deterministic ingestion
- Dependency injection
- No network calls in unit tests
- Fixtures for parsed notes
- E2E tests for parse → ingest

Test structure:

    tests/
        conftest.py
        test_chunker.py            — detect_archetype(), chunk_note(), Chunk dataclass
        test_date_parser.py        — parse_date(), is_date_header(), is_ambiguous_date()
        test_joplin_sync_parser.py
        test_openai_embedding_client.py
        test_notebook_resolution.py
        test_supabase_client.py
        unit/
            test_cli_arguments.py
            test_embedding_wrapper.py
            test_metadata_parsing.py
            test_payload_builder.py
            test_archetype_a.py          — chunk_archetype_a() (milestone 8.9.6)
            test_archetype_b.py          — chunk_archetype_b() (milestone 8.9.6)
            test_archetype_c.py          — chunk_archetype_c() (milestone 8.9.6)
            test_archetype_d.py          — chunk_archetype_d() (milestone 8.9.6)
            test_archetype_e.py          — chunk_archetype_e() (milestone 8.9.6)
            test_resource_extractor.py   — extract_resources() (milestone 8.9.6)
            test_retriever.py            — retrieval logic (milestone 8.9.7 — TODO)
            test_embed_chunks.py         — backfill CLI (milestone 8.9.7 — TODO)
        integration/
            test_pipeline_integration.py
            test_embedding_client_mock.py
            test_idempotency_behavior.py
            test_supabase_client_mock.py
            test_retrieval_api.py        — FastAPI endpoint tests (8.9.7 — TODO)
        e2e/
        fixtures/
        test_data/

Note: flat tests/ root files predate the unit/integration subfolder
structure. Consolidation deferred to a housekeeping pass once the
ingestion and parser test suites grow enough to warrant it.

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
