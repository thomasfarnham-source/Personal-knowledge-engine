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
### System Document Ingestion Boundary (2026-04-01)

System-level documents (ARCHITECTURE.md, ROADMAP.md, governance documents, Fitness OS architecture, vision statements) are **not** part of the PKE ingestion pipeline.

These documents may be mirrored into the Obsidian vault for convenience, but they must not be treated as content sources. They are excluded from:

- Stage 1 parsing
- Stage 2 ingestion
- Embedding generation
- Retrieval API
- Companion and Observer reflection

**Canonical Source**
All system documents remain canonical in GitHub repositories. Obsidian mirrors are convenience copies only.

**Rationale**
This boundary prevents self-referential loops in the reflective corpus and preserves the separation between:

- personal lived experience (journal, messages, history)
- system architecture and governance documents

**Future Extension**
A dedicated ingestion path for system documents may be added later using:

- `source_type = "system_doc"`
- `privacy_tier = 0`
- retrieval filters that exclude system documents except in explicit “architecture mode”

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
(Part 2)
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

(Part 3)
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

(Part 5 )
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
## 22. Content Curation Agent Architecture (milestone 9.15)

A multi-agent content curation system that delivers daily and weekly
briefs to the Obsidian vault.

### Agent Pipeline

    Scout → Editor → Connector → Composer

Sequential. Each agent's output is the next agent's input.
If any stage fails, the pipeline stops and reports which stage failed.

### Agent Responsibilities

    Scout:     Coverage. Scans RSS + NewsAPI. No editorial judgment.
               Follows written mandate (MANDATE.md). No access to
               personal corpus (deliberate — prevents over-filtering).

    Editor:    Taste. Filters via Claude API against three-pillar
               mandate. Also monitors Scout (kill rates by source,
               pillar coverage gaps). Reports to Producer.

    Connector: Adjacency. Queries PKE Retrieval API and book database.
               Does not force connections. Annotates items where genuine
               adjacency exists. Silent where it doesn't.

    Composer:  Assembly. Produces daily drops (markdown, 3-5 items)
               and weekly synthesis (patterns, connections, post seeds).
               Weekly synthesis uses Claude for pattern recognition.

### Governance

    Mandate document (MANDATE.md): stored outside the agents. The
    Producer writes and revises it. The Scout follows it. The Editor
    monitors compliance.

    Agent visibility boundaries:
      Scout    — external sources only, mandate document
      Editor   — Scout output, pillar definitions, kill criteria
      Connector — Editor output, PKE API, book database
      Composer — all upstream output

    Producer review: monthly review of Scout raw output to recalibrate
    sources and mandate language.

### Data Flow

    Sources (RSS, NewsAPI)
        ↓
    output/raw/scout_raw_YYYY-MM-DD.json
        ↓
    output/filtered/editor_filtered_YYYY-MM-DD.json
        ↓
    output/connected/connected_YYYY-MM-DD.json
        ↓
    Obsidian vault/Content Briefs/Daily Drop YYYY-MM-DD.md
    Obsidian vault/Content Briefs/Weekly Synthesis YYYY-WNN.md

### Integration Points

    PKE Retrieval API (localhost:8000) — Connector queries personal
    corpus for semantic adjacency. Same API the Obsidian Reflections
    panel uses.

    Claude API (Anthropic) — Editor uses for filtering judgment,
    Connector uses for connection synthesis, Composer uses for
    weekly synthesis generation. Model: claude-sonnet-4-20250514.

    Book database (books.json) — Connector queries by theme for
    reading adjacency. Populated manually over time.

### Dependencies

    feedparser — RSS parsing
    requests   — HTTP client
    NEWSAPI_KEY — environment variable
    ANTHROPIC_API_KEY — environment variable
    PKE Retrieval API — must be running for Connector

# Security Updates for PKE Documents

---
### Deployment Architecture (designed 2026-04-04)

    Server layer (GitHub Actions):
        Runs daily on cron schedule (6 AM EST)
        Executes: Scout → Editor → Composer
        No personal data involved — scans public sources,
        calls Claude for filtering, produces markdown brief
        Output: daily drop pushed to OneDrive via repo or API
        API keys stored as GitHub Secrets (encrypted, not in code)

    Local layer (Obsidian Shell Commands):
        Triggered on demand by the Producer from Obsidian
        Two commands:
          "Enrich today's brief" — starts PKE API, runs Connector
          against today's daily drop, annotates with personal
          corpus connections, stops API
          "Weekly synthesis" — runs Composer in weekly mode against
          accumulated daily drops from the past 7 days

    Separation principle:
        Public internet scanning runs on server (always available)
        Private corpus access runs locally (never leaves machine)
        Daily drops accumulate automatically
        Enrichment and synthesis happen on the Producer's schedule

---

## 23. Content Curation Agent — Security Model

The content curation agent introduces external data into the local
system for the first time. All previous PKE content sources (Joplin,
iMessage, Yahoo Mail) are personal data already on the machine. The
Scout pulls content from the public internet. This requires a defined
trust boundary.

### What enters the system

The Scout ingests metadata only — titles, URLs, publication dates,
and summary snippets. It does not download full articles, execute
remote code, or fetch arbitrary web content. RSS feeds return
structured XML. NewsAPI returns structured JSON from its own servers.

The Editor and Connector send curated metadata (titles, summaries)
to the Anthropic API for filtering and synthesis. The Connector also
sends PKE retrieval results (journal/message snippets) to Claude for
relevance annotation — this is the same exposure pattern as the
Obsidian plugin's "Why?" button, not a new data flow.

### Trust boundaries

    Tier 1 — Trusted (personal data, never leaves machine except
    via explicit API calls the user controls):
        Joplin corpus, Obsidian vault, iMessage exports,
        Yahoo Mail MBOX files, book database, PKE retrieval API

    Tier 2 — Curated external (known publications, structured
    feeds, metadata only):
        RSS feeds from sources.json, NewsAPI query results

    Tier 3 — Third-party APIs (data sent outbound for processing):
        Anthropic Claude API (Editor filtering, Connector synthesis,
        Composer weekly synthesis)
        NewsAPI (search queries reveal topic interests)
        OpenAI API (embeddings — existing, not new)

### Risk vectors and mitigations

**RSS feed compromise**
    Risk: a feed URL is hijacked or redirected. Malicious content
    injected into title or summary fields could contain markdown
    that renders misleadingly in Obsidian.
    Mitigation: the Scout's _clean_summary() strips HTML tags.
    sources.json contains only known, reputable publications.
    Producer reviews source list quarterly.
    Future: add URL validation check — warn if a feed's domain
    or TLS certificate changes unexpectedly.

**NewsAPI as intermediary**
    Risk: search queries sent to NewsAPI reveal topic interests.
    Free tier API key could be rate-limited or revoked.
    Mitigation: queries are broad topic searches, not personally
    identifying. Use the free tier key with no payment method
    attached. Key stored in .env, never committed to git.

**Outbound data to Claude API**
    Risk: journal and message snippets sent to Anthropic for
    Connector synthesis and Editor filtering.
    Mitigation: this is the same trust relationship already
    established for the Obsidian "Why?" button and embeddings.
    Anthropic's data retention policy applies. No new exposure
    beyond what already exists.
    Note: if the Ollama provider is implemented for the Companion
    Layer, the same local-only option could be extended to the
    content agent — Editor and Connector running against a local
    model with zero outbound data. Quality tradeoff applies.

**Accumulated external data on disk**
    Risk: raw Scout output (JSON files) accumulates over time.
    Creates a growing archive of scraped metadata on the local
    machine with no retention policy.
    Mitigation: implement automatic cleanup — delete raw feed
    files older than 30 days. The daily drops and weekly syntheses
    in the Obsidian vault are the permanent record, not the raw
    Scout output.

**API key exposure**
    Risk: .env file contains NEWSAPI_KEY, ANTHROPIC_API_KEY,
    YAHOO_APP_PASSWORD, OPENAI_API_KEY.
    Mitigation: .env is in .gitignore, never committed. Keys are
    service-specific with minimal permissions. No payment method
    on NewsAPI free tier. Yahoo app password is separate from
    main account password. Rotate keys annually or on suspicion
    of compromise.

### Data flow diagram

    Public Internet (RSS, NewsAPI)
        ↓ metadata only (titles, summaries, URLs)
    Scout → output/raw/ (local, ephemeral, 30-day retention)
        ↓
    Editor → Anthropic API (sends titles + summaries for filtering)
        ↓
    Connector → PKE API (local, no network)
             → Anthropic API (sends titles + PKE snippets for synthesis)
        ↓
    Composer → Obsidian vault (local, permanent)

    No full article content enters the system.
    No personal corpus data leaves the machine except via
    Anthropic API calls (same trust model as existing plugin).

### Retention policy

    output/raw/          — 30 days, then delete
    output/filtered/     — 30 days, then delete
    output/connected/    — 30 days, then delete
    output/briefs/       — permanent (also in Obsidian vault)
    Obsidian vault/Content Briefs/ — permanent, user-managed

### Future considerations

    If the Scout is ever extended to fetch full article content
    (web_fetch), the security model must be revisited. Full content
    fetching introduces risks that metadata-only scanning does not:
    tracking pixels, malformed content, significantly larger storage
    footprint, and potential copyright concerns. Do not add full
    content fetching without a deliberate design decision.


---

## Security Constraints

The Scout operates within defined security boundaries:

- Ingest metadata only (titles, summaries, URLs) — never full articles
- Sources limited to those listed in sources.json — no dynamic discovery
- HTML stripped from all ingested content before storage or rendering
- Raw feed files retained for 30 days maximum, then deleted
- API keys stored in .env, never committed, never logged
- Producer reviews source list quarterly for compromised or stale feeds
- No full article fetching without explicit design decision and
  security review

These constraints are part of the mandate. The Scout must not be
extended beyond metadata ingestion without updating this section.


---
