# Personal Knowledge Engine — System Architecture

Last updated: 2026-03-15 11:16 EST

This document defines the architecture, contracts, and sequencing of the
Personal Knowledge Engine (PKE). It is the authoritative reference for all
system-level reasoning, design decisions, and future development. All AI
tools must treat this document as the source of truth.

---

## 1. System Overview

The Personal Knowledge Engine is a personal intelligence layer with three
faces:

**The pipeline** — a deterministic, two-stage ingestion system that converts
personal notes and messages into a structured, queryable knowledge base
backed by Supabase (or local sqlite-vec) and embeddings.

**The writing environment** — an Obsidian-based writing surface with a
custom plugin that queries the PKE retrieval API in real time, surfacing
semantically relevant chunks from personal history in a live insight panel
as the user writes.

**The companion layer** — a distilled voice derived from years of real
human relationships, operating as an unprompted, unpredictable presence
in the writing environment. Built on the CompanionProvider protocol —
pluggable across frontier models (Claude, GPT-4) and local models (Llama 3
via Ollama). See Section 18.

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
- Local-first architecture — all components can run without internet

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

Multi-source extension fields (optional, added milestone 9.x):
```
    "source_type":      str | None,       # "joplin" | "imessage" | "email" etc.
    "participants":     list[str] | None, # for message sources
    "dominant_sender":  str | None,       # for message sources
    "thread_id":        str | None,       # for message sources
    "thread_type":      str | None,       # "group" | "bilateral"
    "privacy_tier":     int | None,       # 2 = personal/journal
                                          # 3 = bilateral/relational
                                          # default retrieval excludes tier 3
                                          # see Content Privacy Tiering in ROADMAP.md
    "person_ids":       list[str] | None, # RESERVED — entity layer (see Section 17)
                                          # not populated until entity milestone
                                          # every parser must reserve this field
```

Rules:
- No missing fields (core fields)
- No None values (core fields)
- Empty string or empty list for missing core metadata
- Multi-source extension fields default to None if not applicable
- person_ids must be reserved as None by every parser until the
  entity layer is built — never omit this field from the contract

This contract must not change without a formal design decision.

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

### EmbeddingClient Protocol

```python
class EmbeddingClient(Protocol):
    def generate(self, text: str) -> list[float]: ...
```

Implementations:
    OpenAIEmbeddingClient  — calls OpenAI API (current)
    DummyEmbeddingClient   — deterministic, for tests
    OllamaEmbeddingClient  — local model via Ollama (planned)

Swap the provider — nothing else changes. This is the pattern
the CompanionProvider protocol (Section 18) follows exactly.

---

## 12. Supabase Integration

Tables:
- notebooks
- tags
- notes (with embeddings)
- note_tags (relationships)
- chunks (with embeddings, populated milestone 8.9.7)

Planned tables (milestone 9.x — iMessage Parser):
- imessage_threads
- imessage_participants
- imessage_messages
- imessage_bursts (primary retrieval target, with embedding column)

Planned tables (milestone 9.13 — Yahoo Mail / Entity Layer):
- contacts                — cross-channel identity registry
- contact_identifiers     — multiple identifiers per contact
  (phone, email, apple_id, display_name)

These tables are not source-specific. They serve as the shared
identity layer across all content channels. See Section 17.

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

Local database alternative (planned):
    sqlite-vec — SQLite with vector extension, full local operation.
    Replaces Supabase for privacy-first and offline deployments.
    SupabaseClient abstraction already isolates all DB calls —
    swapping the backend is a client implementation change only.
    See Cross-Cutting Concerns in ROADMAP.md.

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
    "query":              "string",
    "notebook":           "string (optional)",
    "date_from":          "YYYY-MM-DD (optional)",
    "date_to":            "YYYY-MM-DD (optional)",
    "limit":              "int (optional, default 5, max 20)",
    "recency_preference": "string (optional): 'older' | 'recent' | 'none'"
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
Isolated for future extension. Planned signals in priority order:
    1. Recency decay — user-configurable preference (favour older /
       favour recent / no preference). Exposed in Obsidian plugin
       settings UI and passed as recency_preference parameter.
       Tilts the scoring curve — does not create hard cutoffs.
       Applies uniformly across all content types (unified timeline
       principle).
    2. Archetype weighting — oral history vs journal fragments
    3. Timestamp confidence — explicit > calculated > null

CORS middleware: added to allow Obsidian plugin origin.
    Permitted origins: app://obsidian.md, http://localhost,
    http://127.0.0.1
    Not using allow_origins=["*"] — content is personal and sensitive.

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

### Obsidian Insight Plugin (milestone 8.9.8 — COMPLETE)

Repo: thomasfarnham-source/pke-obsidian-plugin
Language: TypeScript
Built: 2026-03-14

File structure:
    src/
        main.ts          — entry point, wires all components
        types.ts         — shared types, mirrors Python API contract
        api.ts           — HTTP client for PKE retrieval API
        query-engine.ts  — debounce, pause gate, context extraction
        insight-view.ts  — sidebar panel rendering reflections
        settings.ts      — settings tab UI

A custom Obsidian plugin that:
1. Watches the active note for changes
2. After a short debounce (~1000ms), sends current paragraph +
   2-3 preceding lines to POST /query
3. Renders top 3-5 reflections in a right sidebar panel
4. Displays: date, note title, relevant passage (raw text)
5. Never generates AI summaries — surfaces raw content only

Settings UI (human-framed):
- Refresh speed (Immediately / After a moment / Only when I stop)
- Result count (3 / 5 / 7)
- Notebook filter (All / current / multi-select)
- Recency preference (Favour older / Favour recent / No preference)
- Note exclusion tag (default: #private)

Features:
- Cold start: fires initial query from last session context on load
- Link feature: one-click inserts dated Obsidian link at cursor
- Relevance feedback: thumbs up/down and dismiss, logged locally
- Note exclusion: user-configurable tag, filtered client-side

Post-launch improvement backlog:
- Query scope control — selection mode (highlight text to trigger)
- HTML stripping — Joplin export artefacts in matched_text
- Navigation/deep links — non-functional until Joplin → Obsidian
  migration complete
- Relevance ranking — personal relevance scoring deferred to 8.9.9

**The insight panel is never a dead end.**
Every surfaced passage links back to its full source context.
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

### Yahoo Mail Parser Design (milestone 9.13 — IN PROGRESS)

Extraction method: IMAP via export.imap.mail.yahoo.com
    Yahoo provides two IMAP endpoints. The standard server
    (imap.mail.yahoo.com) caps folder visibility at 10,000 messages
    and SEARCH results at ~1,000. The export server
    (export.imap.mail.yahoo.com) removes these limits. Same
    credentials, same app password, same port (993/SSL).

    IMAP SEARCH is capped on both servers. FETCH by UID has no cap.
    All extraction uses UID-based FETCH, never SEARCH.

Authentication: Yahoo app password (not main account password)
    Generated at login.yahoo.com/account/security → External connections.
    Requires two-step verification enabled on Yahoo account.
    Stored in .env as YAHOO_EMAIL and YAHOO_APP_PASSWORD.

Two-pass extraction strategy:

    Pass 1 — Header scan (indexing)
        FETCH headers for all messages in all folders by UID.
        Store in local SQLite index (working data, disposable).
        Headers: From, To, CC, Date, Subject, Message-ID,
        In-Reply-To, References.
        Purpose: contact identification and volume analysis
        before committing to full download.

    Pass 2 — Selective download
        Query header index for messages involving target contacts.
        FETCH full RFC822 bodies for matched messages by UID.
        Save to MBOX files in pke-data/yahoo-mail/.
        MBOX files become the source of truth for the parser
        (same role as iMazing CSV exports for iMessage).

    Pass 3 — Parse and ingest
        MBOX files → yahoo_mail_parser.py → ParsedNote contract
        → orchestrator → Supabase.
        Standard pipeline — identical flow to Joplin and iMessage.

Source format: MBOX (standard mailbox format)
    Python's built-in mailbox module parses MBOX natively.
    Each email is a full RFC822 message with all headers and body.

Unit of ingestion: email thread (grouped by In-Reply-To/References)
    Individual emails within a thread are analogous to messages
    within an iMessage burst. Thread grouping uses the References
    and In-Reply-To headers, which form a reply chain.
    Fallback: Subject-based threading for emails lacking these headers.

HTML handling:
    Most Yahoo Mail bodies are HTML. Same strip_html() approach as
    Joplin archetype chunkers — strip tags, decode entities,
    preserve prose content.

Deduplication: Message-ID header (unique per email, RFC2822 standard).

Privacy tier: Tier 3 (bilateral/relational), same as iMessage bilateral.

Contact resolution:
    Email addresses resolved against contacts + contact_identifiers
    tables in Supabase (Entity Layer — see Section 17).
    Multiple addresses per person supported (e.g. William Renahan
    has both blackstone.com and dpimc.com addresses across different
    employment periods).

New database tables:
    contacts              — cross-channel identity registry
    contact_identifiers   — multiple identifiers per contact
    (See Section 17 for schema — these tables serve all sources,
    not just Yahoo Mail.)

    No Yahoo-specific tables needed. Email content flows through
    the existing chunks table via the ParsedNote contract, same
    as all other sources.

Known limitations:
    - Export IMAP server caps Inbox at 100,000 visible messages
    - IMAP SEARCH results capped at ~1,000 per query
    - Work email replies (UBS, Citi, Barclays addresses) are not
      in the Yahoo mailbox and are irrecoverable
    - Pre-2006 email not present

---
### Plain Text Is Always the Source of Truth
The database is an index, never an archive. Re-ingestion from source
files is always possible and always safe. The database should never
be treated as the source of truth for content reconstruction.

### Migration Strategy (Joplin → Obsidian)
See ROADMAP.md milestone 9.x — Obsidian Parser + Migration for the
full four-phase migration plan including validation gate.

### Planned Parsers
- pke/parsers/obsidian_parser.py (primary writing surface migration)
- pke/parsers/imessage_parser.py (iMessage threads — milestone 9.x)
- pke/parsers/yahoo_mail_parser.py (email from select senders)
- pke/parsers/handwritten_journal_parser.py (Moleskine digitization)

### iMessage Parser Design (milestone 9.x — IN PROGRESS)

Extraction tool: iMazing (imazing.com) — $29.99 one-time, 1 device
Source format: iMazing CSV export (17 columns, ISO timestamps)
Unit of ingestion: conversation burst (4-hour gap threshold)

CSV columns:
    Chat Session, Message Date, Delivered Date, Read Date,
    Edited Date, Deleted Date, Service, Type, Sender ID,
    Sender Name, Status, Replying to, Subject, Text,
    Reactions, Attachment, Attachment type

Sender resolution:
    Outgoing + blank Sender Name → Thomas (self)
    All others → display name from Sender Name column

New database tables:
    imessage_threads      — conversation containers
    imessage_participants — identity registry (v1: phone + name)
    imessage_messages     — atomic message records
    imessage_bursts       — retrievable units with embedding column

Thread attribute on burst:
    Every burst carries thread_id linking to imessage_threads.
    Enables filtering by thread type (group vs bilateral).
    Bilateral and group registers are distinct — Patrick one-on-one
    with Thomas is a different voice than Patrick in the group.

Identity resolution (v1):
    Primary key: phone number + display name composite.
    Known limitation: numbers and names can change over time.
    Full Person/PersonIdentifier model deferred — see Section 17.

### Conversation Model (milestone 9.13)

A conversation is defined by its exact participant set, not by
topic, thread, or time. Tom + Pat is one conversation spanning
years. Tom + Pat + James is a different conversation.

    Conversation — unique participant set (SHA256 hash of sorted list)
    Thread — topical exchange within a conversation (References chain)
    Burst — time-segmented cluster within a thread (4h gap threshold)

When participants change (added or dropped), a new conversation
is created. Linking across participant set changes is deferred
to a future milestone.

This model applies across channels. The Tom + Pat conversation
exists in both email (2007-2026) and iMessage bilateral (2018-
present). The Entity Layer (contacts table) is what links them
through identifier resolution.

Table: email_conversations
    Keyed by participant_hash (SHA256 of sorted participant list).
    Stores participant list, counts, date range.
    One row per unique participant set.
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
            test_retriever.py            — retrieval logic (milestone 8.9.7 ✅)
            test_embed_chunks.py         — backfill CLI (milestone 8.9.7 ✅)
        integration/
            test_pipeline_integration.py
            test_embedding_client_mock.py
            test_idempotency_behavior.py
            test_supabase_client_mock.py
            test_retrieval_api.py        — FastAPI endpoint tests (8.9.7 ✅)
        e2e/
        fixtures/
        test_data/

Note: flat tests/ root files predate the unit/integration subfolder
structure. Consolidation deferred to a housekeeping pass once the
ingestion and parser test suites grow enough to warrant it.

Test count as of milestone 8.9.8: 385 passing, 0 failing.

---

## 17. Entity Layer (Planned)

A cross-channel identity layer that sits above all parsers.
Allows the same person, place, or event to be recognised and
linked across multiple content channels.

Primary use case: "Patrick Mangan" in an iMessage thread and
"Pat" in a journal entry resolve to the same Person entity.

### The Problem
Without the entity layer, the system retrieves by semantic
similarity — "find things that feel like this." But it cannot
answer relationship queries — "find everything about Pat" or
"find everything that happened in Ireland." Every reference
across channels is currently an island.

### The Person Entity

```python
Person:
    person_id        # permanent, never changes
    canonical_name   # "Patrick Mangan"
    aliases          # ["Pat", "PJM", "Patrick", "Mangan"]
    first_known_date # when they first appear in any channel
    channels         # which content channels they appear in
    notes            # human-added context

PersonIdentifier:    # mutable, append-only
    identifier_id
    person_id        # links to Person
    identifier_type  # "phone" | "apple_id" | "display_name"
    identifier_value # "+16467327168"
    date_first_seen
    date_last_seen
    confidence       # "confirmed" | "inferred"
```

Known limitations: phone numbers and display names can change
over time. The PersonIdentifier model handles this by treating
identifiers as append-only — a new number adds a new record,
old messages still resolve via the old number.

### The Broader Entity Pattern

Same concept applies to:
    People       — Pat, James, Killian, Ger, family members
    Places       — Ireland, specific recurring locations
    Organisations — Citi, specific institutions
    Events       — recurring annual events, named trips
    Concepts     — recurring ideas that span channels

### Two Retrieval Modes Enabled

    Semantic retrieval — find by meaning (current)
    Entity retrieval   — find by person, place, event (planned)

Together significantly more powerful than either alone.

### The person_ids Field Rule

Every parser must include person_ids as an optional field
in its ParsedNote output — even if it cannot populate it.
The field must exist before entity resolution logic is built
so no migration is needed when it arrives.

    person_ids: list[str] | None = None  # reserved, always present

### Build Sequence

    Now   — person_ids reserved in ParsedNote contract ✅
    Soon  — entity extraction for iMessage participants
    Later — named entity recognition across Joplin corpus
    Much  — full entities table, cross-channel resolution,
    later   relationship graph

---
### Entity Layer — Implementation Seed (milestone 9.13)

The Yahoo Mail parser is the first milestone that requires cross-channel
identity resolution at build time, not just as a reserved field. The
same person (e.g. William Renahan) appears with multiple email addresses
across different employers, and must also be linkable to iMessage
participant records.

The contacts and contact_identifiers tables will be created in Supabase
as part of milestone 9.13. Schema follows the Person/PersonIdentifier
model defined in this section, scoped to the minimum viable structure:

    contacts:
        contact_id          UUID PRIMARY KEY
        canonical_name      TEXT NOT NULL
        created_at          TIMESTAMPTZ DEFAULT now()
        notes               TEXT          -- human-added context

    contact_identifiers:
        identifier_id       UUID PRIMARY KEY
        contact_id          UUID REFERENCES contacts(contact_id)
        identifier_type     TEXT NOT NULL  -- "email" | "phone" | "apple_id" | "display_name"
        identifier_value    TEXT NOT NULL
        source              TEXT           -- "yahoo_mail" | "imessage" | "manual"
        date_first_seen     TEXT
        date_last_seen      TEXT
        created_at          TIMESTAMPTZ DEFAULT now()
        UNIQUE(identifier_type, identifier_value)

    This schema is deliberately minimal. It will grow as the entity
    layer matures, but the core principle is established: one contact,
    many identifiers, across all channels.

    iMessage participants (imessage_participants table) can be migrated
    into this model when convenient — not a blocker for 9.13.

Updated build sequence:
    Now   — person_ids reserved in ParsedNote contract ✅
    9.13  — contacts + contact_identifiers tables created in Supabase
            Populated with target email contacts + known identifiers
            Yahoo Mail parser resolves against these tables
    Next  — iMessage participants migrated into contacts model
    Later — Named entity recognition across Joplin journal corpus
    Much  — Full cross-channel resolution, relationship graph
    later

---
## 18. Companion Layer Architecture (Planned)

The third face of the PKE. A distilled voice derived from years
of real human relationships, operating as an unprompted presence
in the writing environment.

### CompanionProvider Protocol

Same pattern as EmbeddingClient. Any provider that implements
this interface is a valid companion engine.

```python
class CompanionProvider(Protocol):
    def generate(
        self,
        system_prompt: str,
        context: list[str],
        journal_excerpt: str,
    ) -> str: ...
```

Planned implementations:
    ClaudeCompanionProvider   — Anthropic API (start here)
    OpenAICompanionProvider   — OpenAI API
    OllamaCompanionProvider   — local Llama 3 via Ollama
    GeminiCompanionProvider   — Google API

Provider and PersonalitySkin are independent.
Swap either without touching the other.

### PersonalitySkin

A configuration object — separate from the provider,
separately editable, separately versioned.

```python
PersonalitySkin:
    name                # "Book Club", "Family", etc.
    system_prompt       # core personality descriptor
    channel_weights     # per-sender retrieval weights
    era_filter          # date range for retrieval
    response_modes      # direct / attributed / synthesis
    register_weights    # direct / ironic / oblique / nostalgic
    max_response_length # one sentence / two / three
    trigger_threshold   # resonance score required to speak
    cadence_limit       # max interventions per session
```

The system_prompt is the heart of the skin. Written by the
producer after corpus analysis — not generated automatically.
Specifics over adjectives. See ROADMAP.md Companion Layer.

### Three-Level Document Architecture

Three portrait documents feed the companion and observer layers:

    Level 1 — Writer Portrait (person level)
        About Thomas as an individual. Context for the Observer.
        Built from passive corpus inference + active conversation.
        Template: WRITER_PORTRAIT_TEMPLATE.md

    Level 2 — Thread Portrait (relationship level)
        About a specific conversation context.
        One document per thread. Built from corpus analysis.

    Level 3 — Voice Profile (person-within-thread level)
        How a specific person shows up in a specific thread.
        Used by Companion Engine for channel weighting.
        Built from per-sender corpus analysis.

### Observer Layer

A reasoning model that watches the journal being written,
has been provided the Writer Portrait, sees what the retrieval
engine surfaces, and comments on the relationship between
current writing and past history.

The writer can respond directly to Observer comments — these
conversations are flagged for incorporation into the Writer
Portrait at the next update cycle. The writer is an active
collaborator in their own portrait, not just its subject.

### Local Operation

All companion and observer functionality can run on Llama 3
via Ollama — no internet required. Quality degrades compared
to frontier models but core functionality is preserved.

See ROADMAP.md Companion Layer for full milestone sequence.

---

## 19. Local-First and Resilience Architecture

The PKE is designed to operate without internet connectivity.
This serves two goals: privacy and resilience.

### Privacy
Personal journal content, family history, medical logs, and
relationship corpus never need to leave the user's machine.

### Resilience
In scenarios where internet infrastructure is unavailable,
the entire PKE stack continues to function.

### The Fully Sovereign Local Stack

    Notes corpus        — Joplin sync folder (OneDrive, always-offline)
    Obsidian vault      — local app, local Markdown files
    Embeddings/index    — sqlite-vec (replaces Supabase — planned)
    Retrieval API       — FastAPI + uvicorn, runs locally
    Embedding model     — Ollama local model (replaces OpenAI — planned)
    Companion voice     — Llama 3 via Ollama
    Observer layer      — Llama 3 via Ollama
    General knowledge   — Llama 3 training data (Wikipedia + web corpus)

### Local Model Setup

    Tool: Ollama (ollama.com)
    Model: Llama 3 (8B variant for standard laptops)
    Download: ollama pull llama3  (~4-8GB, one-time)
    Serve: ollama serve
    API: http://localhost:11434 (same interface pattern as OpenAI)

### Current External Dependencies

    Supabase    — embeddings and index (migrate to sqlite-vec)
    OpenAI API  — embedding generation (migrate to Ollama)
    Anthropic   — companion/observer generation (Ollama as fallback)

All three are isolated behind protocol interfaces. Replacing any
one of them is a client implementation change only — the pipeline,
retrieval logic, and plugin are untouched.

---

## 20. Collaboration Workflow

Development follows a three-step loop:
- Design (Thomas + Claude)
- Implement (VS Code Copilot)
- Review (Thomas + Claude)

All decisions are recorded in CURRENT_TASK.md.
ARCHITECTURE.md is the authoritative reference and must be updated
whenever a structural decision changes.
ROADMAP.md captures strategic direction and must be updated when
vision or milestone sequencing changes.
WRITER_PORTRAIT_TEMPLATE.md captures the Observer context document
structure and will be populated through corpus analysis + Thomas
annotation.



## 21. Unified Retrieval Architecture (milestone 9.13+)

All content sources write retrievable content to a single table:
retrieval_units. One embedding column, one vector search RPC, one
place to tune retrieval quality.

### The Problem
The original match_chunks RPC used LEFT JOINs to search across
chunks (Joplin) and imessage_bursts (iMessage). Every new source
required a migration to the RPC function and added a join. At 5+
sources this becomes fragile and slow.

### The Solution
A single retrieval_units table that every source writes to:

    retrieval_units:
        id              UUID
        source_type     TEXT    — "joplin" | "imessage" | "email"
        source_id       TEXT    — FK to source-specific table
        body            TEXT    — the retrievable content
        embedding       vector(1536)
        title           TEXT
        notebook        TEXT
        created_at      TIMESTAMPTZ
        participants    TEXT[]
        privacy_tier    INTEGER
        dominant_sender TEXT
        thread_id       TEXT
        thread_type     TEXT
        metadata        JSONB

Source-specific tables (imessage_bursts, email_conversations,
email_messages, chunks) store structural metadata. The retrieval
content lives in one place.

### The RPC
match_retrieval_units — simple vector search, no joins:
    Takes: query_embedding, match_count, filter_notebook, max_privacy_tier
    Returns: matching rows ranked by cosine similarity
    Privacy tier filtering built in (default tier 2 excludes
    bilateral/relational content unless explicitly requested)

### Migration Path
1. retrieval_units created (SQL migration written, milestone 9.13)
2. Email ingestor writes to it first
3. Backfill existing Joplin chunks and iMessage bursts
4. match_chunks simplified or deprecated
5. Future sources write to retrieval_units from day one
6. Obsidian plugin updated to query match_retrieval_units