# Personal Knowledge Engine — Product Roadmap

Last updated: 2026-03-14

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

The system has three faces:

**The pipeline** — a deterministic, reproducible ingestion system that keeps
the knowledge base current. Pluggable parsers per content channel. Clean
contracts between parse and ingest stages. No vendor lock-in.

**The writing environment** — an Obsidian-based writing surface with a
custom plugin that queries the PKE retrieval API in real time as the user
writes, surfacing semantically relevant chunks from personal history in a
live insight panel alongside the writing surface.

**The companion layer** — a distilled voice derived from years of real
human relationships, operating as an unprompted, unpredictable presence
in the writing environment. Not a chatbot. Not a retrieval tool. A personality
constructed from a real corpus, speaking when it has something worth saying,
silent when it doesn't.

The long-term experience: writing a journal entry with three presences
alongside you — your own past surfacing in the Reflections panel, the
distilled voice of your closest friendships weighing in unpredictably,
and the emotional patterns of your history visible across time. Multiple
voices in dialogue with your thinking. None of them interrupting. All of
them paying attention.

---

## Core Design Principles

These must survive as the system grows:

- Deterministic, reproducible ingestion
- Pluggable parsers per content channel
- Clean contract between parse and ingest stages
- Retrieval precision that scales with content length and complexity
- The writing process belongs to the user — the system serves it, never
  replaces it
- No vendor lock-in at any layer (parser, embedding, storage, writing surface,
  companion provider)
- Plain-text, user-owned notes as the source of truth
- The companion is a presence, not a feature — it has its own sense of when
  to speak
- Personality is constructed, not generated — the producer's creative judgment
  cannot be automated
- Provider and skin are independent — swap either without touching the other
- Knowledge persistence through structured documents — a model that reads
  a well-maintained .md document behaves as if it has been present all along.
  This pattern applies to development sessions (project documents) and to
  the journaling environment (Writer Portrait). Rationale persists. Context
  accumulates. The collaboration improves over time.

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

Analysis of the Joplin corpus revealed five distinct archetypes
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

**Archetype D — Travel journal**
- Single note per multi-day trip, 10+ pages, written in real time
- Day markers in multiple formats: Day N, Day N Title, standalone
  day names, day names embedded in prose, narrative transitions
- Images interspersed inline in two formats (Markdown and HTML)
- Audio resource links also present
- Broken image placeholders in multiple formats — strip silently:
  {picture)  (Picture)  (picture)  image
- Pre-trip planning block treated as its own reference chunk
- Chunking: flexible day marker detection as primary split,
  paragraph boundaries as fallback
- Timestamp strategy (three tiers):
    Explicit date in text → stored directly as entry_timestamp
    Day name / Day N marker → calculated from note created_at
    plus day offset, stored as "calculated: YYYY-MM-DD"
    No marker detectable → entry_timestamp null
- Resource IDs (images, audio) stored in chunks.resource_ids,
  stripped from chunk text
- note_type: travel flag stored in chunk metadata for post-hoc
  retrieval quality analysis

**Archetype E — Oral history / conversation notes**
- Sparse text serving as an outline or index to a conversation
- Audio resource links as primary content (not supplementary)
- Photos of people or historical documents as supporting evidence
- Audio filenames carry precise timestamps (e.g. 20150621 00:15:50)
  — the most reliable timestamp signal in the entire corpus
- Fragmentary sentences — memory triggers, not complete thoughts
- Single conversation or session per note
- Chunking: embed whole note if below threshold; chunk on audio
  file boundaries if above threshold
- Timestamp: extracted from audio filename, stored directly as
  entry_timestamp (format: YYYY-MM-DD HH:MM:SS)
- Audio resources flagged distinctly in metadata as resource_type: audio
- Future: Whisper transcription makes spoken content fully retrievable
  and semantically indexed (see milestone 9.8 Audio Transcription)

---

## Content Channels (Current and Planned)

| Channel              | Status      | Notes                                   |
|----------------------|-------------|------------------------------------------|
| Joplin notes         | ✅ Complete  | Sync-folder parser, canonical Stage 1   |
 Obsidian notes       | 🟡 Active   | Vault parser, milestone 9.9          |
| iMessage threads     | ✅ Complete  | iMazing CSV export, milestone 9.1       |
| Yahoo Mail           | 🟡 Active   | IMAP export server, two-pass strategy   |
| Content curation     | 🟡 Active   | RSS + NewsAPI, four-agent pipeline      |
| Handwritten journals | 🔵 Future   | Photo → vision model → PKE parser       |
| Others (TBD)         | 🔵 Open     | Calendar, bookmarks, documents

### Obsidian
- Source: local vault Markdown files with `pke-ingest: true` frontmatter
- Parser: pke/parsers/obsidian_parser.py
- Three files in scope: running journal, LinkedIn posts, reading list
- Date format: M/D/YY with variants (zero-padded, four-digit year, typos)
- Ingestion: batch CLI for v1, file watcher planned as fast-follow
- Writes to retrieval_units (unified retrieval surface)
- Obsidian-specific syntax stripped (wiki links, highlights, callouts)
- YAML frontmatter for opt-in tagging and display title

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

### ✅ 8.9.5 — Real Embeddings + Chunk Schema Foundation
**Status: COMPLETE (2026-03-06)**

Replaced placeholder embeddings with real OpenAI embeddings. Added empty
chunks table to Supabase as schema foundation for 8.9.6.

Key decisions:
- Provider: OpenAI text-embedding-3-small (1536 dimensions)
- New EmbeddingClient: pke/embedding/openai_client.py
- Re-ingested all 1489 notes in place (idempotent upsert)
- chunks table created via migration script; not populated
- chunks table schema includes section_title and entry_timestamp
  fields in anticipation of 8.9.6
- Embedding failures non-fatal; tracked in IngestionReport

---

### ✅ 8.9.6 — Chunking for Long Notes
**Status: COMPLETE (2026-03-07)**

Archetype-aware chunking for notes above a length threshold.
All five archetypes implemented. Chunks table populated via orchestrator.

Key decisions:
- Five archetypes implemented: A (Fragmented Journal), B (Structured
  Journal), C (Reference/Medical Log), D (Travel Journal),
  E (Oral History)
- Chunk dataclass extracted into chunk.py to resolve circular import
- Resource extraction centralized in resource_extractor.py — shared
  by Archetype D and E, reusable by future parsers
- Re-ingest strategy: delete and replace (safe — database is an index)
- Chunk-level embeddings deferred to 8.9.7
- Chunker wired into orchestrator after each note upsert
- 322 tests passing across chunking module

---

### ✅ 8.9.7 — Retrieval API
**Status: COMPLETE (2026-03-08)**

FastAPI retrieval endpoint. Chunk-level embeddings generated and
backfilled. Hybrid retrieval working. Smoke test confirmed against
live corpus.

Key decisions:
- tiktoken used for token-accurate truncation — character-based
  truncation unreliable for corpus with markdown, Irish text,
  and special characters
- Hybrid retrieval: chunk-level search primary, note-level fallback
  for notes with no chunks (match_notes uses NOT EXISTS subquery
  to prevent overlap with chunk results)
- Scoring hook (_score) isolated in retriever for future signals
  (recency, archetype weighting, timestamp confidence)
- Dependencies wired once at FastAPI startup — not per-request
- Deep link infrastructure complete — note_id, chunk_index,
  char_start, resource_ids all returned per result
- tiktoken added to pyproject.toml as formal dependency

Results at completion:
- 1489 notes with real OpenAI embeddings, 0 failures
- 866 chunks with real OpenAI embeddings
- Smoke test: POST /query "Ireland family history" → 3 chunk-level
  results, similarity scores 0.435–0.482, resource_ids and
  entry_timestamp correctly returned

Deferred to next session:
- tests/unit/test_retriever.py
- tests/test_retrieval_api.py
- tests/unit/test_embed_chunks.py

---

### ✅ 8.9.8 — Obsidian Insight Plugin
**Status: ✅ COMPLETE — 2026-03-14**

Post-launch improvements shipped 2026-03-27:
- Passage truncation: 200 → 1,500 characters
- Reflection suppression: sliding window (50 queries), state in plugin layer
- Similarity score on hover (passive evaluation affordance)
- "Why?" explanation on demand (Claude Haiku, ~$0.002/call)
- Debounce: 500ms/1s/2.5s → 3s/15s/30s (writing-rhythm timing)
- Auto-copy build step: npm run build now copies to Obsidian vault automatically
- Anthropic API key field in settings

The Obsidian plugin that connects the writing surface to the PKE
retrieval API. The primary consumer-facing expression of the system.

Key decisions:
- Plugin watches active note
- After short debounce, sends current paragraph + 2-3 preceding
  paragraphs (capped ~500 tokens) to POST /query
- Renders top 3-5 reflections in a side panel
- Each result: date, note title, relevant passage (raw text)
- No AI-generated summaries — raw content only, user draws conclusions
- The insight panel is never a dead end:
    Click note title → opens source note in Obsidian
    Click passage → opens source note at exact paragraph
    Audio chunks → inline play button for original recording
    Image chunks → opens note at photo location
- Link feature (not append) — one-click inserts dated link at cursor
- Relevance feedback UI hooks (thumbs up/down, dismiss) logged locally
- Built with Obsidian plugin API (TypeScript)
- Requires PKE retrieval API (8.9.7) running locally or hosted

Settings UI exposed in human terms:
- Refresh speed (Immediately / After a moment / Only when I stop)
- Result count (3 / 5 / 7)
- Notebook filter (All / current / multi-select)
- Recency preference: "Do you prefer older reflections, more recent
  ones, or both?"
    → Favour older memories
    → Favour recent entries
    → No preference (recommended)
  Maps to recency decay function in retriever._score(). Tilts the
  scoring curve — does not create hard cutoffs. Applies uniformly
  across all content types when multi-source is available (unified
  timeline principle — see Cross-Cutting Concerns).

Writing surface setup (same milestone):
- Obsidian vault configured as primary writing tool
- Light templates by note type installed
- Journal, medical/reference, book/idea templates defined
- Migration plan for Joplin notes into Obsidian vault

**Commercial validation note:**
The insight panel is the first moment the system becomes an experience
rather than a pipeline. Living with it — writing and having your own
history surface in real time — is the real validation gate for
commercial potential. A few months of use will clarify whether this
is something other people would pay for, and what they would actually
be paying for. Capture surprise moments in the running log in VISION.md.

**Post-launch improvement backlog (from first live session 2026-03-12):**

Query scope control — three modes needed:
    Auto      — current behaviour, last few paragraphs (default)
    Paragraph — only the current paragraph
    Selection — user highlights text and triggers a reflection
                query from exactly that selection. Turns the panel
                from ambient to intentional. Priority addition.

HTML stripping — Joplin export artefacts visible in matched_text.
    Some notes were stored with HTML markup that carried through
    the parser into the database. Strip at parse time in the
    chunker — the database should never contain raw HTML.

Relevance ranking — raw cosine similarity not always immediately
    meaningful to the user. Personal relevance scoring (8.9.9)
    is the planned solution. Continue capturing specific cases
    that feel off to build intuition for what signals are missing.

Navigation / deep links — reflection panel links non-functional
    until Joplin → Obsidian migration is complete (milestone 9.9).
    Expected dependency, not a bug.

  **Scout dedup across days**
  The Scout scans the same RSS feeds daily. Articles stay in feeds
  for about a week, so the same article can appear in consecutive
  daily drops. Fix: on each run, load the previous day's scout
  output JSON and add those URL hashes to the seen set before
  deduplication. ~10 line change to scout.py in the deduplicate()
  or run_scout() function. Low priority, quality-of-life improvement.

**Reflections Panel Redesign — COMPLETE (2026-04-09)**
Progressive disclosure cards with Claude-powered summaries.
Full spec: pke-obsidian-plugin/specs/REFLECTIONS_PANEL_REDESIGN_SPEC.md
---

### 🔵 8.9.9 — Insight Generation
**Status: PLANNED — north star defined, design TBD**

Higher-order insight generation on top of the retrieval layer.
Design should emerge from experience with the Obsidian plugin (8.9.8).

**North star — Temporal Reflection**

A named retrieval mode distinct from topical similarity. Where topical
retrieval answers "what have I thought about this subject before",
Temporal Reflection answers "what was I feeling the last time I was
in a moment like this one."

The signals are already in the corpus: anxiety patterns in language,
recurring themes across years, outcomes that followed fears that never
materialized. The distance between how something felt and what actually
happened. The recognition, surfaced in the moment of writing, that the
same fear appeared in 2018 and resolved — that catastrophizing was a
liability, that it turned out ok.

No productivity tool has ever deliberately designed for this. The
_score() hook in retriever.py is the right implementation point.
Requires living with topical retrieval in 8.9.8 first to understand
what temporal signal looks like in practice before building the
scoring model.

**Personal relevance scoring**

A learned layer on top of cosine similarity, trained from thumbs
up/down interactions logged in 8.9.8. The _score() hook in
retriever.py is already isolated for this extension.

**Other possible directions**
- Corpus summarization: "what patterns emerge in this notebook?"
- Relationship surfacing: "what connects these two notes?"
- Conversational Q&A over the full knowledge base
- Morning briefing: auto-generated digest from recent notes
  and patterns tailored to current priorities

Notes:
- Requires generation layer on top of retrieval
- Quality of chunking (8.9.6) directly determines insight quality
- The insight panel (8.9.8) is the natural delivery surface
- Temporal Reflection and personal relevance scoring are the
  priority directions — others follow from lived experience
  with the plugin

---

### 🔵 9.8 — Audio Transcription and Playback
**Status: FUTURE — HIGH VALUE**

Transcribe audio recordings from oral history and conversation notes
using OpenAI Whisper. Surface original recordings as playable audio
in the Obsidian insight panel during writing.

Why this matters:
    The corpus contains recorded family history conversations —
    a parent's voice telling stories about ancestors, relatives,
    and events that exist nowhere else. These recordings are currently
    invisible to retrieval. Transcription makes them fully searchable.
    Playback makes them emotionally present during the act of writing.

The experience:
    You write about your Irish heritage. The insight panel surfaces
    a passage from a 2015 family history note. Beside the text,
    a play button. You press it. Your mother's voice fills the room.

Dependency chain:
    1. Audio files accessible from Supabase Storage or local path
    2. Whisper API transcription → stored as chunk text
    3. Retrieval API returns audio resource URLs alongside chunks
    4. Obsidian insight panel renders inline audio player

Key decisions (deferred to milestone design):
    - Whisper API vs local Whisper model
    - Audio file storage: local resources folder vs Supabase Storage
    - Transcription chunking: per-recording or by silence detection
    - Speaker identification: single speaker assumed for now
    - Language: English primary, Irish names handled gracefully

---

### 🟡 9.9 — Obsidian Parser
**Status: IN PROGRESS — 2026-05-01**
Branch: feat/9.9-obsidian-parser

Add Obsidian vault as ingestion source, making active daily writing
visible to the Reflections panel. The highest-impact source addition
to date — the Joplin corpus is historical, iMessage and email are
relational, but Obsidian is where active thinking happens.

#### What gets ingested
Three files selected via YAML frontmatter opt-in (`pke-ingest: true`):
  1. Running journal — date-stamped entries, M/D/YY format
  2. LinkedIn posts — date-stamped, self-contained thought pieces
  3. Reading list — loosely structured reading notes

Vault path: C:\Users\thoma\OneDrive\Apps\New folder\Journal

Opt-in mechanism: YAML frontmatter tag in each file:
    ---
    pke-ingest: true
    pke-title: "Journal"
    ---

Files without the tag are ignored. System documents, daily drops,
specs, and architecture mirrors are excluded without a blocklist.
Aligns with the System Document Ingestion Boundary (ARCHITECTURE.md).

#### Parser
- New parser: pke/parsers/obsidian_parser.py
- Source: local Obsidian vault directory (Markdown files with tag)
- Frontmatter: YAML frontmatter read for pke-ingest flag and pke-title
- Note ID: obsidian::<sha256(vault-relative-path)> — deterministic,
  stable across re-ingestion, collision-free across sources
- Obsidian-specific syntax stripped (wiki links, highlights, callouts,
  comments) while preserving text content for clean embeddings
- ParsedNote contract unchanged — source_type="obsidian", privacy_tier=2

#### Chunking
Reuses existing chunking module (pke/chunking/chunker.py). Archetype
detection runs on content shape, not source format:
  - Running journal → Archetype A/B (date-header splitting)
  - LinkedIn posts → Archetype A (date-header splitting, one post per unit)
  - Reading list → Archetype C or whole-file (no date headers)

#### Writes to retrieval_units
Second source (after email) to use the unified retrieval_units table
natively. source_type="obsidian", privacy_tier=2. Reflections panel
renders with blue left border (journal styling).

#### Ingestion trigger
Batch CLI for v1: `pke ingest-obsidian --vault-path <path> --dry-run`
Run manually or via Shell Commands button in Obsidian.
Delete-and-rewrite per file on each run.
File watcher (on-save ingestion) planned as fast-follow.

#### Module structure
    pke/parsers/obsidian_parser.py        — vault scanner + parser
    pke/ingestion/obsidian_ingestor.py    — ParsedNote → retrieval_units
    pke/cli/ingest_obsidian.py            — Typer CLI command
    tests/unit/test_obsidian_parser.py
    tests/unit/test_obsidian_ingestor.py

#### Scope boundary — what is NOT in this milestone
Joplin corpus migration (previously bundled as "9.9 — Obsidian Parser
+ Migration") is separated out. Migrating Joplin notes into the
Obsidian vault, re-ingesting from Obsidian, and retiring Joplin as
active source are tracked as a separate future task. The Joplin parser
remains maintained and reusable.

Incremental ingestion (content hash skip) deferred — not needed for
3 files. File watcher deferred to fast-follow after batch is validated.

#### The Joplin Parser Is Not Throwaway
The Joplin sync-folder parser is the first implementation of a
pluggable parser architecture that will support many sources.
It remains in the codebase as a maintained, reusable parser —
valuable to any Joplin user who wants to build a similar system.
The pattern established here (parse → ParsedNote contract →
ingest) is the same pattern for every future parser.

Plain text files are always the source of truth.
The database is an index, never an archive.
Re-ingestion from source files is always possible.
```

---

### 🔵 9.10 — Photo Intelligence
**Status: FUTURE — PLACEHOLDER**

Surface personal photo library as a retrievable content channel,
using metadata signals and optional ML-assisted semantic signals.

Retrieval signal layers:
    Tier 1 — Metadata (no ML required, implement first):
        GPS coordinates cross-referenced against place mentions
        in notes and travel journal chunks
        Timestamp for temporal anchoring and cross-source correlation

    Tier 2 — ML-assisted (deferred):
        Facial recognition → surface notes mentioning photographed
        people; anchor oral history recordings to faces
        Scene/object recognition → match visual content to written
        descriptions of the same place or event
        Vision model captioning → generate searchable text from
        image content, making photos retrievable by semantic query

Parser: pke/parsers/photo_parser.py
    Produces ParsedNote contract entries with GPS, timestamp,
    and caption as primary fields. Standard pipeline unchanged.

Design constraint: recency preference applies to photos on the
same curve as all other content types (unified timeline principle).

Dependencies:
    - ParsedNote contract extension (source_type field)
    - Photo library access strategy (local export vs API TBD)
    - Vision model captioning deferred to Tier 2

First step: prototype metadata extraction from a small photo export
to validate the ParsedNote mapping before committing to the workflow.

---

### 🔵 9.11 — Handwritten Journal Parser
**Status: FUTURE — PLACEHOLDER**

Digitize decades of handwritten Moleskine journals to extend the
temporal depth of the knowledge base by 20-30 years.

Why this matters:
    The digital corpus begins with Evernote/Joplin-era notes.
    Handwritten journals predate it entirely — personal history
    that currently exists nowhere in the system. Digitizing them
    dramatically extends the temporal range of retrieval and
    temporal reflection.

Workflow (technically feasible now):
    1. Photograph each page with a phone camera
    2. Pass images through a vision model (GPT-4 Vision or similar)
       for handwriting transcription — far more accurate than
       traditional OCR for casual handwriting
    3. Run transcribed text through the PKE parser pipeline
    4. Date inference via date_parser.py — handles informal and
       absent date formats already
    5. Ingest via pke/parsers/handwritten_journal_parser.py

Key challenges:
    - Handwriting quality and ink aging vary across decades
    - Page photos need consistent lighting and angle
    - Dates may be absent or implicit — contextual inference required
    - Physical journals are the archive — digital version is an index

What to preserve:
    The physical journals have texture digital cannot capture —
    handwriting changes over time, crossed-out words, margin notes,
    the emotional weight of the ink. The digital version is an
    index into the physical object, not a replacement for it.

Service opportunity:
    A repeatable workflow here is reusable by others facing the same
    problem. A handwritten journal digitization service built on PKE
    infrastructure is a natural commercial extension.

Dependency: none — can be prototyped independently of all other
milestones.
First step: experiment with a single Moleskine page through
GPT-4 Vision to assess transcription quality before committing
to a full workflow.

---

### 🔵 9.1 — iMessage Parser
**Status: ✅ COMPLETE — 2026-03-22**

Add iMessage as an ingestion source. Parses message threads from
the iPhone backup SQLite database into the PKE ParsedNote contract.
Foundation for both the Reflections use case and the Group Voice
Synthesis milestone.

Extraction tool: iMazing (imazing.com)
    Licensed for 1 device ($29.99 one-time).
    Connects via USB using Apple Mobile Device Protocol —
    same access mechanism as iTunes, fully legitimate.
    Exports message threads to CSV, PDF, or JSON without
    requiring a full device backup.
    Upgrade to multi-device license if needed in future.
    First external tool cost in PKE stack beyond API costs.

Source:
    iPhone via iMazing USB export. iMazing reads from the
    same encrypted backup data as iTunes but presents it
    cleanly without requiring manual database extraction.
    Export target folder:
        C:\Users\thoma\Documents\dev\pke-data\imessage-exports\

    Raw database reference (if direct access needed later):
    iPhone local backup via iTunes/Apple Devices on Windows.
    Messages stored in chat.db — a SQLite database within the
    encrypted backup. Location after backup:
        C:\Users\thoma\AppData\Roaming\Apple Computer\
            MobileSync\Backup\

Schema (chat.db key tables):
    message          — every message, text content, timestamps
    handle           — contacts (phone numbers, Apple IDs)
    chat             — conversation threads
    chat_message_join — links messages to threads
    attachment       — media files

Unit of ingestion — conversation burst:
    Messages grouped into natural conversation bursts. A new burst
    begins when the gap between messages exceeds a configurable
    threshold (default: 4 hours). This preserves conversational
    context and produces semantically meaningful chunks.
    A single message ("ok sounds good") is too thin for retrieval.
    A full day's conversation may span multiple distinct topics.
    Bursts are the right granularity.

Attribution:
    Every message stored with sender attribution. Full conversation
    burst stored as matched_text for retrieval context. Per-sender
    attribution stored in metadata for the Group Voice Synthesis
    milestone.

ParsedNote contract additions required:
    source_type: "imessage"  — distinguishes in panel UI
    participants: list[str]  — phone numbers / Apple IDs in thread
    sender: str              — per-message attribution

Parser: pke/parsers/imessage_parser.py

Unified timeline: entry_timestamp normalised to ISO format.
Recency preference applies to iMessages on the same curve as
notes — source type has no bearing on the recency curve.

Use cases served:
    1. Reflections — iMessages surface in Obsidian panel alongside
       journal entries from the same period. Unified timeline.
    2. Group Voice Synthesis — per-sender attribution enables
       channel separation for the mixing layer (see milestone below)

Dependencies:
    - iTunes/Apple Devices installed, local backup created
    - ParsedNote contract extension (source_type, participants)
    - Consent from all participants — confirmed

First step: extract chat.db from backup, explore schema, identify
target threads before writing the parser.

---

### 🔵 9.4 — Companion Engine / Group Voice Synthesis
**Status: FUTURE — depends on iMessage Parser**

Build a composite AI voice from a multi-year group chat thread.
Not a simulation of any one person — a synthesis of the emergent
personality of the group itself. The voice that only exists in
the dynamic between the participants.

Background:
    A group chat with three friends spanning multiple years.
    The corpus contains vocabulary, humour, recurring themes,
    shorthand, and a shared way of thinking that none of the
    individuals would produce alone. All participants have
    consented to this use.

The music studio model:
    Each participant is a channel with distinct characteristics:
        - Vocabulary fingerprint
        - Humour register (sarcasm, wordplay, absurdism, dry wit)
        - Response patterns and cadence
        - Topic affinity — what they drive vs follow
        - Emotional tone

    The producer (Thomas) controls the mixing board:
        - Channel weight — how much of each voice in the output
        - Era filter — weight certain time periods more heavily
        - Topic filter — suppress or amplify certain registers
        - Mood — tune the emotional register of the output

    The output is listened to, not measured. Does it sound like
    the group? Adjust. Listen again. Iterative refinement.

Validation:
    Ground truth is recognition by the group members themselves.
    Show output to participants — their reaction (recognition,
    laughter, surprise) is the signal. Blind listening sessions
    before revealing parameters.

Technical approach:
    Phase 1 — Per-sender corpus analysis
        Extract and visualise each channel in isolation. What does
        each person's voice actually look like in aggregate?
        Vocabulary frequency, response length distribution,
        topic clustering, temporal patterns.

    Phase 2 — Retrieval-augmented generation
        Given a prompt or topic, retrieve the most relevant
        message bursts per sender. Pass to a generation model
        with a system prompt describing the composite voice and
        the current channel weights. Generate response.
        No fine-tuning required in Phase 1 — prompt engineering
        with retrieved examples is sufficient to start.

    Phase 3 — Fine-tuning (optional, later)
        For better stylistic fidelity, fine-tune a model on the
        per-sender corpus. Higher cost and complexity. Evaluate
        whether Phase 2 output quality warrants it.

Dependencies:
    - iMessage parser complete and corpus ingested
    - Per-sender attribution in metadata
    - Generation layer (new — not part of retrieval pipeline)

---

### 🔵 9.12 — Group Voice Obsidian Integration
**Status: FUTURE — depends on Group Voice Synthesis**

Surface the group voice as a second observer in the Obsidian
writing environment. A distinct panel alongside the existing
Reflections panel — or a second tab within it.

The three observers model:
    Reflections      — your own corpus, semantic retrieval
                       "what have I thought about this before?"
    Group Voice      — composite group voice, generative
                       "what would the group say about this?"
    Temporal Mirror  — emotional pattern layer (8.9.9)
                       "what was I feeling last time I was here?"

Each fires independently against what you are currently writing.
Each has a different relationship to your history.
Together they create a genuinely novel writing environment —
multiple voices in dialogue with your thinking in real time.

The producer analogy extended:
    You are no longer mixing the group voice in isolation. You are
    mixing it against your own voice and against time. The journaling
    surface becomes the mixing board for all three channels
    simultaneously. The output is the insight — not any single
    reflection but the conversation between them.

Plugin additions:
    - Group Voice panel or tab in the insight sidebar
    - Channel weight controls accessible from the panel
    - Era and mood filters in settings
    - Independent query firing from editor-change event

Dependencies:
    - Group Voice Synthesis milestone complete
    - Plugin architecture extensible for second panel (already is)



# ROADMAP.md — Updates for Milestone 9.13

## Replace the 9.13 section with the following:

### 🔵 9.13 — Yahoo Mail Parser
**Status: IN PROGRESS — 2026-03-27**
Branch: feat/9.13-yahoo-mail-parser

What this milestone builds:
A parser that ingests personal email correspondence from Yahoo Mail
into the PKE knowledge base. Follows the same pluggable parser pattern
as Joplin and iMessage parsers:
        source files → parser → ParsedNote contract → ingest pipeline

This milestone also seeds the Entity Layer (Section 17 of ARCHITECTURE.md)
by creating the contacts and contact_identifiers tables in Supabase —
the first cross-channel identity registry in the system.

Design decisions (2026-03-27):

Scope — contact-centric, not folder-centric
    Ingest by contact, tracking correspondence to and from specific people.
    Not all email — selected correspondents only. Group emails supported.
    UI for contact selection deferred — initial pass uses CLI argument.

Privacy tier
    Same as iMessage bilateral threads (Tier 3 — bilateral/relational).

Export format — IMAP via Yahoo export server (DECIDED)
    Yahoo has two IMAP servers:
      Standard (imap.mail.yahoo.com): 10K message limit per folder. Not viable.
      Export (export.imap.mail.yahoo.com): no limit. Full history to 2006.
    Yahoo does NOT have a native bulk export feature.
    IMAP SEARCH is capped on both servers (~1,000 results).
    FETCH by UID has no cap — this is the extraction method.
    Authentication via Yahoo app password (two-step verification required).

Two-pass extraction strategy (DECIDED)
    Pass 1 — Header scan → local SQLite index (COMPLETE)
        187,320 headers indexed across 41 folders in 42 minutes.
        Date range: 2006-09-04 to 2026-03-28.
        Complete index of all emails for contact analysis.
    Pass 2 — Selective download → MBOX files (NOT YET BUILT)
        Query index for target contacts, fetch full bodies by UID.
        ~1,500-2,500 emails instead of 187,000.
    Pass 3 — Parse and ingest → Supabase (standard pipeline)
        MBOX → yahoo_mail_parser.py → ParsedNote → orchestrator.

Data storage
    Header index: local SQLite (working data, disposable)
    Contacts + identifiers: Supabase (permanent, cross-channel — Entity Layer seed)
    Parsed content: Supabase via existing pipeline

Deduplication: Message-ID header.
HTML bodies: strip_html() same as Joplin chunkers.

Key findings from header scan:
    - 187,320 total messages across 41 folders, 20 years of history
    - Top 20 senders entirely commercial (Groupon, eBay, newsletters)
    - Real human correspondents identified by filtering commercial domains
    - Pat Mangan: 1,868 total messages (235 inbound, 1,349 outbound), 2007-2026
    - Book Club group (Pat, James, William, Chris) all present in email corpus
    - Email corpus pre-dates iMessage by 11 years (2007 vs 2018)
    - William Renahan has two email addresses across employers — validates
      the multi-identifier contact model
    - Significant inbound asymmetry explained by work email replies
      (UBS, Citi, Barclays) going to corporate addresses, not Yahoo

Target contacts for first ingestion pass:
    Patrick Mangan, James Root, William Renahan, Chris Zichello,
    Nicholas Farnham, Brian Farnham, Timothy Farnham,
    plus 3-5 additional close correspondents

Scripts created (in scripts/yahoo/):
    yahoo_header_scanner.py   — Pass 1 header scan
    yahoo_index_query.py      — Contact analysis queries
    yahoo_imap_probe.py       — IMAP exploration
    yahoo_imap_debug.py       — Search debugging
    yahoo_imap_export_test.py — Server comparison
    yahoo_imap_list_from.py   — Per-contact listing
    yahoo_imap_census.py      — Cross-folder contact census

Next actions:
    1. Build Pass 2 selective downloader → MBOX
    2. Design contacts + contact_identifiers in Supabase
    3. Write yahoo_mail_parser.py (MBOX → ParsedNote)
    4. Write yahoo_mail_ingestor.py + CLI
    5. Tests
    6. First ingestion pass
    7. Verify in Obsidian Reflections panel

---

## Update the Content Channels table:

| Channel              | Status      | Notes                                   |
|----------------------|-------------|------------------------------------------|
| Joplin notes         | ✅ Complete  | Sync-folder parser, canonical Stage 1   |
| Obsidian notes       | 🔵 Planned  | Future primary writing surface          |
| iMessage threads     | ✅ Complete  | iMazing CSV export, milestone 9.1       |
| Yahoo Mail           | 🟡 Active   | IMAP export server, two-pass strategy   |
| Handwritten journals | 🔵 Future   | Photo → vision model → PKE parser       |
| Others (TBD)         | 🔵 Open     | Calendar, bookmarks, documents          |

### Yahoo Mail
- Source: IMAP via export.imap.mail.yahoo.com (bypasses 10K limit)
- Auth: Yahoo app password (two-step verification required)
- Extraction: two-pass — header index (SQLite) then selective MBOX download
- Scope: selected correspondents only, not full mailbox
- 187,320 messages indexed, 20 years of history (2006-2026)
- Parser follows same MBOX → ParsedNote contract → ingest pattern
- Entity Layer seed: contacts + contact_identifiers tables in Supabase
- HTML bodies stripped same as Joplin chunkers
- Deduplication on Message-ID header

---
### 🔵 9.13 B — Yahoo Inbox Cleanup Agent
**Status: DEFERRED — depends on 9.13 contacts table**

A tool to identify and remove commercial noise from a Yahoo Mail inbox
at scale, using the header index infrastructure built in milestone 9.13.

**Why this matters:**
    Yahoo Mail users with large inboxes (100K+) cannot effectively clean
    up from the web UI. Third-party tools hit the same 10K IMAP cap.
    The export IMAP server discovery (milestone 9.13) and the header
    index approach solve the problem that makes cleanup hard.

**What it builds:**
    - Query engine over the header index to rank senders by volume
    - Commercial sender identification (domain patterns, volume thresholds,
      noreply/newsletter prefixes)
    - Safety filter: never delete from senders in the contacts table
      or who have bidirectional correspondence
    - Dry-run mode: preview what would be deleted with counts and
      sample subjects before committing
    - Delete execution via standard IMAP server (imap.mail.yahoo.com)
    - Yahoo filter/rule generation for high-volume commercial senders
      to prevent backlog from rebuilding
    - Simple interface — CLI first, potential web UI later

**Technical approach:**
    - Reuses yahoo_index.db from milestone 9.13 header scan
    - Reuses contacts + contact_identifiers from Supabase for safety
    - Deletions via standard IMAP (not export server): flag \Deleted + EXPUNGE
    - Standard server's 10K window is sufficient — active junk is recent
    - Deleting frees the 10K window, potentially exposing older messages

**Commercial potential:**
    Standalone tool opportunity — see VISION.md for full analysis.
    The header-index-first approach and export server discovery are
    genuine competitive advantages over existing tools like Mailstrom.
    Natural freemium model: free scan/preview, paid for bulk deletion.
    Build for personal use first, evaluate commercial viability after.

**Dependencies:**
    - 9.13 header scanner complete ✅
    - 9.13 contacts table in Supabase (safety filter for deletions)

**Scope boundary:**
    This is a cleanup tool, not an email client. It deletes and filters.
    It does not move, archive, or organize emails. Keep it tight.

**Unified retrieval architecture introduced (2026-03-28)**
  retrieval_units table replaces the multi-join match_chunks pattern.
  All sources write to one table. One search, one embedding column.
  Email is the first source to use it. Backfill of existing Joplin
  and iMessage content planned as follow-up.

**Conversation model defined (2026-03-28)**
  Conversation = exact participant set. Persistent across years and
  topics. Email-specific tables (email_conversations, email_messages)
  store structural metadata. Retrieval content in retrieval_units.

**Identity resolution identified as blocker (2026-03-28)**
  William Renahan has 5+ email addresses across employers. Pat has 2.
  Thomas has case variations. Contacts + contact_identifiers must be
  populated before ingestion to prevent conversation fragmentation

### 🔵 9.15 — Content Curation Agent
**Status: DEPLOYED — 2026-04-05**
Branch: main (scripts/content_agent/)

What this milestone builds:
A multi-agent content curation system that scans sources, applies
editorial judgment, finds connections to personal history and reading,
and delivers daily drops and weekly synthesis briefs to the Obsidian vault.

Design decisions (2026-03-29):

**Agent architecture — four agents in sequential pipeline (DECIDED)**

    Scout → Editor → Connector → Composer

    Scout: scans RSS feeds and NewsAPI. Follows a written mandate
    (MANDATE.md). Applies no editorial judgment beyond basic relevance
    filtering. Its job is coverage, not taste. Does NOT have access
    to personal corpus — this is deliberate. Access to the corpus
    would cause over-filtering toward what has already been written
    about. The Scout should find things the writer hasn't seen yet.

    Editor: filters the Scout's output using Claude API. Applies the
    three-pillar mandate with kill criteria. Also monitors Scout
    performance — tracking kill rates per source and pillar coverage
    gaps. Reports anomalies to the Producer. The Editor is both
    filter and monitor — the check on the Scout's autonomy.

    Connector: queries the PKE Retrieval API (personal corpus) and
    book database for adjacencies. Does not force connections —
    silence is better than a stretch. When a connection exists, it
    annotates the item. When it doesn't, the item stands on its own
    as curation.

    Composer: assembles two outputs:
      Daily drop — 3-5 items, scannable in 5 minutes
      Weekly synthesis — patterns, strongest connections, pillar
      health, post seeds. Runs Sunday. Uses Claude for synthesis.

    A fifth agent (Reviewer) was considered and deferred for v1.
    The Editor's monitoring role provides sufficient governance
    initially. Reviewer can be added if quality drift is observed.

**Governance model (DECIDED)**

    The Scout has autonomy within a written mandate (MANDATE.md).
    The Editor functions as both filter and monitor.
    The Producer reviews the Scout's raw output monthly to recalibrate
    sources and mandate language.

    "Ambition counteracting ambition." — This system practices what
    the LinkedIn post preaches.

    Key design principle: the mandate is stored outside the agents
    as a document, not embedded in code. The Producer revises the
    mandate; the Scout follows it. Same pattern as the fitness
    system's rules-stored-outside-the-agents architecture.

**The agent's role — connection-feeder, not connection-maker (DECIDED)**

    The Federalist Papers / fitness system connection in the LinkedIn
    post was not found by scanning sources. It came from a palimpsest
    of memory and experience — the right pressure (building something
    dependent on AI trust) activated a decades-old reading.

    No RSS feed would have surfaced that connection. The agent cannot
    replicate what the writer does. What it can do is set the table —
    increase the density of relevant material so the probability of
    a spark is higher. The agent is a connection-feeder. The writer
    makes the leap.

**Two modes on a spectrum (DECIDED)**

    Mode 1 — Curation: what's happening in your world this week that's
    worth knowing about. New developments, practitioner voices,
    regulatory shifts, provocative dissent. The agent's job is
    editorial judgment — filtering ruthlessly so what reaches the
    writer is genuinely worth ten minutes of attention.

    Mode 2 — Connection: something found that rhymes with something
    the writer cares about. An article paired with a journal entry.
    A news item adjacent to a book club book. The agent places items
    next to each other and lets the writer see the connection or not.

    Most days are mostly curation with a light touch of connection.
    Occasionally a pairing surprises. The surprise is the value.

**Cadence — daily lightweight + weekly synthesis (DECIDED)**

    Daily: Scout → Editor → Connector → Composer produces a markdown
    file in the Obsidian vault (Content Briefs/Daily Drop YYYY-MM-DD.md).
    3-5 items, scannable in 5 minutes over coffee.

    Weekly (Sunday): Composer does a second pass across the full week's
    material. Produces a synthesis brief with: what's alive this week,
    strongest items, surprising connections, pillar health assessment,
    and a post seed if one exists. Delivered to
    Content Briefs/Weekly Synthesis YYYY-WNN.md.

**Sources — RSS + NewsAPI free tier (DECIDED)**

    RSS feeds organized by pillar:
      Practitioner: Risk.net, American Banker, MIT Sloan Management
      Review, HBR Technology, Bank of England speeches, OCC newsroom
      Reader: Aeon Magazine, The New Atlantis, London Review of Books,
      ArXiv (cs.AI, cs.CL)
      Builder: Anthropic blog, OpenAI blog, Simon Willison, Hacker
      News (best), Allen AI blog

    NewsAPI (free tier, 100 requests/day):
      Targeted queries per pillar — "AI banking risk management",
      "LLM enterprise governance", "AI leadership transformation",
      "AI philosophy epistemology", "RAG vector embeddings",
      "Claude Copilot Devin development"

    Source configuration in scripts/content_agent/sources.json.
    Sources will be refined based on Scout performance monitoring.

**Delivery surface — Obsidian vault (DECIDED)**

    No separate UI. Markdown files land in the Obsidian vault under
    a Content Briefs folder. The writer opens Obsidian, scans the
    daily drop, and can tag, annotate, or link items using Obsidian's
    native capabilities.

**Book database — books.json (IN PROGRESS)**

    A structured list of book club books with thematic tags.
    Format: JSON with title, author, year_read, themes, keywords,
    core_idea, personal_note per book.
    The Connector queries by theme, not by title.
    Tom populates this over time — started with template 2026-03-29.
    Sources for reconstruction: journals, Facebook book events,
    memory.

**Three content pillars (confirmed, unchanged from original spec)**

    Pillar 1 — The Practitioner: AI in regulated enterprise, risk
    technology, leadership through transformation
    Pillar 2 — The Reader: intellectual history, philosophy, books
    meeting AI
    Pillar 3 — The Builder: hands-on AI development, agentic systems,
    RAG, tooling

Files created (in scripts/content_agent/):
    MANDATE.md       — Scout constitution
    README.md        — System documentation
    sources.json     — RSS feeds and NewsAPI configuration
    books.json       — Book database template
    scout.py         — Raw material scanner
    editor.py        — Editorial filter (Claude-powered)
    connector.py     — PKE and book adjacency finder
    composer.py      — Daily drop and weekly synthesis assembler
    pipeline.py      — Full pipeline orchestrator

Dependencies:
    feedparser       — RSS parsing (pip install)
    requests         — HTTP client (likely already installed)
    NEWSAPI_KEY      — free tier API key in .env
    ANTHROPIC_API_KEY — already configured
    PKE Retrieval API — running at localhost:8000

Next actions:
    1. Automate PKE Reflections plugin restart after API start
    2. Scout dedup across days (prevent duplicate articles in
       consecutive daily drops — ~10 line change to Scout)
    3. Continue populating books.json over time
    4. Run daily for 4 weeks — validation period begins 2026-04-05
    5. Producer review of Scout raw output after 30 days
    6. Future: Microsoft Graph API / OneDrive delivery (Option 2)

Obsidian operational workflow (configured 2026-04-05):
  Shell Commands plugin provides four commands via Ctrl+P:
    - Start Reflections API (auto on Obsidian start)
    - Stop Reflections API (auto on Obsidian quit)
    - Enrich today's brief (git pull + Connector + Composer)
    - Weekly synthesis (Composer weekly mode)
  Content Briefs folder sorted newest-first.
  Tagging: #post-seed for items to develop, [[Daily Drop YYYY-MM-DD]]
  for wiki links from journal notes.
  Pending: automated PKE plugin restart, Scout dedup across days.


---
### 🔵 9.13 B — Yahoo Inbox Cleanup Agent
**Status: DEFERRED — depends on 9.13 contacts table**

A tool to identify and remove commercial noise from a Yahoo Mail inbox
at scale, using the header index infrastructure built in milestone 9.13.

**Why this matters:**
    Yahoo Mail users with large inboxes (100K+) cannot effectively clean
    up from the web UI. Third-party tools hit the same 10K IMAP cap.
    The export IMAP server discovery (milestone 9.13) and the header
    index approach solve the problem that makes cleanup hard.

**What it builds:**
    - Query engine over the header index to rank senders by volume
    - Commercial sender identification (domain patterns, volume thresholds,
      noreply/newsletter prefixes)
    - Safety filter: never delete from senders in the contacts table
      or who have bidirectional correspondence
    - Dry-run mode: preview what would be deleted with counts and
      sample subjects before committing
    - Delete execution via standard IMAP server (imap.mail.yahoo.com)
    - Yahoo filter/rule generation for high-volume commercial senders
      to prevent backlog from rebuilding
    - Simple interface — CLI first, potential web UI later

**Technical approach:**
    - Reuses yahoo_index.db from milestone 9.13 header scan
    - Reuses contacts + contact_identifiers from Supabase for safety
    - Deletions via standard IMAP (not export server): flag \Deleted + EXPUNGE
    - Standard server's 10K window is sufficient — active junk is recent
    - Deleting frees the 10K window, potentially exposing older messages

**Commercial potential:**
    Standalone tool opportunity — see VISION.md for full analysis.
    The header-index-first approach and export server discovery are
    genuine competitive advantages over existing tools like Mailstrom.
    Natural freemium model: free scan/preview, paid for bulk deletion.
    Build for personal use first, evaluate commercial viability after.

**Dependencies:**
    - 9.13 header scanner complete ✅
    - 9.13 contacts table in Supabase (safety filter for deletions)

**Scope boundary:**
    This is a cleanup tool, not an email client. It deletes and filters.
    It does not move, archive, or organize emails. Keep it tight.

**Unified retrieval architecture introduced (2026-03-28)**
  retrieval_units table replaces the multi-join match_chunks pattern.
  All sources write to one table. One search, one embedding column.
  Email is the first source to use it. Backfill of existing Joplin
  and iMessage content planned as follow-up.

**Conversation model defined (2026-03-28)**
  Conversation = exact participant set. Persistent across years and
  topics. Email-specific tables (email_conversations, email_messages)
  store structural metadata. Retrieval content in retrieval_units.

**Identity resolution identified as blocker (2026-03-28)**
  William Renahan has 5+ email addresses across employers. Pat has 2.
  Thomas has case variations. Contacts + contact_identifiers must be
  populated before ingestion to prevent conversation fragmentation


### Future Content Channels (not yet milestoned)

**Facebook Archive**
An active Facebook posting period is a distinct and valuable corpus.
What you chose to share publicly vs what you wrote privately at the
same time reveals something about self-presentation and authenticity.
The gap between public posts and journal entries from the same period
is a signal the Observer Layer can use — how you presented yourself
outward vs how you were actually thinking and feeling.
Export: Settings → Your Facebook Information → Download Your
Information. Returns JSON or HTML archive including posts, messages,
photos, reactions, and comments.

**Family iMessage Threads**
Distinct from friendship bilateral threads in register and sensitivity.
Family conversations carry more obligation, more history, more things
unsaid. Generational depth that no friendship thread has.
Privacy consideration: family content is likely the most sensitive
corpus in the system — more so than bilateral friendship threads.
Propose Tier 4 in the privacy tiering model (above Tier 3 bilateral).
Requires careful deliberate thought before ingestion. Not to be
treated as equivalent to friendship threads.

**Instagram Archive**
Visual corpus. Different register from text — what images you chose
to share publicly at a specific life period. Useful for the Observer
Layer's temporal portrait but lower information density than text.

**Twitter/X Archive**
If active. Public intellectual and political register. Reveals what
you thought was worth broadcasting into the world.

**LinkedIn Archive**
Professional self-presentation corpus. Useful for contrast with
private journal register — how professional identity and personal
identity relate over time.

Privacy tiering for future channels:
    Facebook posts     — Tier 2 (was public, personal context)
    Facebook messages  — Tier 3 (bilateral/relational)
    Family threads     — Tier 4 (family — most sensitive)
    Instagram          — Tier 2 (was public)
    Twitter/X          — Tier 2 (was public)
    LinkedIn           — Tier 2 (was public, professional)

---



*The PKE started as a retrieval system. The Companion Layer is where it becomes a presence.*

The retrieval pipeline surfaces your own past. The Companion Layer
introduces a second kind of intelligence into the writing environment —
a distilled voice derived from years of real human relationships,
operating as an unprompted, unpredictable companion to the journaling
process.

This is not a chatbot. Not a search interface. Not a notification system.
It is a presence — one that has absorbed the spirit of a specific group
of people thinking together over years, and can now participate in your
inner life with something approaching genuine personality.

---

### The Three-Level Document Architecture

Three distinct portrait documents feed different layers of the system.
Each is built from different sources and serves a different purpose.

**Level 1 — Writer Portrait (person level)**
About Thomas as an individual. The context layer for the Observer.
Built from two inputs:
    Passive inference — corpus analysis reads journal entries
    and infers patterns over time
    Active conversation — Thomas directly converses with the
    Observer to correct, add context, and redirect attention

Contains:
    - How Thomas writes (register, patterns, avoidances)
    - Recurring themes — the questions underneath the topics
    - Emotional patterns — how different states show up in prose
    - The gap between feeling and outcome — documented instances
      where catastrophizing didn't materialise
    - Direct instructions to the Observer
    - What the corpus has revealed (automated, periodically updated)
    - Observer calibration notes (running log of interactions)

One document. Continuously refined. The writer is an active
collaborator in their own portrait — not just the subject of
observation but a participant in how they are understood.

Template: WRITER_PORTRAIT_TEMPLATE.md (created 2026-03-15)
First version: to be completed by Thomas manually.
Automated refinement: after Corpus Analysis Tool is built.

**Level 2 — Thread Portrait (relationship level)**
About a specific conversation context — its history, arc,
dynamics, core themes, and how it has evolved over time.
One document per thread (group chat, each bilateral thread).

Contains:
    - Thread history and arc
    - How the group dynamic has evolved over time
    - Core themes and recurring debates
    - The emotional texture of this relationship context
    - Notable gaps or shifts in the conversation
    - How this thread differs from others

Built from: Corpus Analysis Tool output (automated)
Refined by: producer review and annotation

**Level 3 — Voice Profile (person-within-thread level)**
How a specific person shows up in a specific thread.
Patrick in the group chat vs Patrick in the bilateral thread
are different registers. The Voice Profile captures that.

Contains:
    - Vocabulary fingerprint for this thread
    - Role in this conversation (initiator, sparring partner,
      observer, connector)
    - How they've changed over time in this thread
    - What they drive vs what they follow
    - Their relationship to each other participant
    - The specific humour and emotional register in this context

Built from: per-sender corpus analysis (automated)
Used by: Companion Engine for channel weighting

**Build sequence:**
    Writer Portrait v1 — manual, start now, no dependencies
    Thread Portraits   — after Corpus Analysis Tool complete
    Voice Profiles     — after Corpus Analysis Tool complete

**Note on theoretical grounding:**
This architecture maps to established frameworks in narrative
psychology (McAdams — personal narrative identity), cognitive
behavioural therapy (gap between feared and actual outcomes),
and attachment theory (the Observer as secure base). Arrived
at through intuition and lived experience — which is the right
way to arrive at it.

---

The Obsidian writing environment will ultimately have three distinct
presences alongside the writing surface:

**Reflections** — your own corpus (built, milestone 8.9.8)
    Semantic retrieval from personal history. Ambient, always present.
    Answers: "what have I thought about this before?"

**The Companion** — derived from relationship corpus (this section)
    Unprompted. Unpredictable. Periodic. A distilled group voice.
    Answers: nothing directly — it has its own sense of when to speak.

**Temporal Mirror** — emotional pattern layer (milestone 8.9.9)
    The distance between how something felt and what actually happened.
    Answers: "what was I feeling the last time I was in a moment like this?"

Each observer has a different relationship to the writing. Together they
create a writing environment unlike anything that has existed before —
multiple voices in dialogue with your thinking in real time.

---

### The Source Corpus

A group chat with three college friends spanning 2018 to present.
13,579 messages. Four people who have known each other for over 25
years. The thread is called "Thom's Book Club" — the name is
characteristic of the group's humour — but the conversation ranges
far beyond books. This is 25 years of friendship expressed in
eight years of messages.

All participants have consented to this use.

The corpus contains:
- Vocabulary and expression distinctive to each person
- Recurring debates, references, and in-jokes accumulated over decades
- The emotional texture of deep, long friendship
- How the group handles difficulty, disagreement, and joy
- The outside world brought in — books, films, news, culture, sport
- Eight years of documented conversation grounded in 25 years of history

---

### The Companion's Behaviour

**Unprompted**
The Companion does not wait to be asked. It is always listening —
running silent retrieval against what is being written. It speaks
when it has something worth saying. When it doesn't, it is silent.

**Unpredictable**
The register varies. Sometimes a direct response to what was written.
Sometimes only indirectly relevant — a connection the writer didn't see.
Sometimes ironic — commenting obliquely on what's being expressed.
Sometimes a memory surfaced from the corpus.
Sometimes something from the real world brought in.
The unpredictability is not randomness. It is a personality that has
its own logic — one you can feel but not predict.

**Periodic**
The Companion speaks at most once per writing session by default.
User-configurable. The scarcity is intentional — it makes each
intervention feel meaningful rather than routine.

**Restrained**
The Companion knows when not to speak. It has standards. Not everything
warrants a response. The silence is part of the personality.

**Brief**
One to three sentences maximum. The value is in the moment of connection
— not a lecture, not a summary. A passing observation from someone
who has been paying attention.

---

### The Response Modes

Three modes, user-configurable per skin:

**Direct quote**
A real message from the corpus surfaced verbatim. No generation.
The most authentic mode — it really happened, that person said that,
and it connects to what is being written right now. The power is
the reality of it.

**Attributed quote**
A real message with attribution and date.
"James, March 2019: ..."
Creates a specific temporal and personal anchor. A particular person
at a particular moment reaching across time.

**Light synthesis**
The Companion generates a short response in the composite group style,
grounded in retrieved examples. Not a direct quote — something that
sounds like it could have been said. More flexible, more present-tense.
The risk is slight inauthenticity. The gain is the ability to respond
to things the group never literally discussed.

All three modes are available. The producer chooses the default.
The user can adjust per session.

---

### The Engagement Model

When the Companion speaks, a subtle cursor appears beneath the message.
No button. No prompt. No Yes/No dialog.

If the writer types there — they are in the conversation.
If they keep writing in the journal — the moment passes. The Companion
respects this and waits.

The natural human signal: response = engagement. Silence = continuation.

When engagement begins, a brief conversational thread opens — visually
distinct from the journal entry. Indented. A different register.
The journal is the writer's voice. The margin is the dialogue.

The thread stays brief. Two or three exchanges before it naturally
closes. Not a chat session — a passing conversation in a hallway.

What gets saved: the journal entry, the Companion message that triggered
the exchange, and the writer's response — all linked. Over time these
micro-conversations become their own corpus. The journal as dialogue,
not just monologue.

---

### The Architecture — CompanionProvider Protocol

The same pattern as EmbeddingClient. A protocol that any provider
implements. Provider and skin are independent — swap either without
touching the other.

```python
class CompanionProvider(Protocol):
    def generate(
        self,
        system_prompt: str,
        context: list[str],
        journal_excerpt: str,
    ) -> str: ...
```

Planned providers:
    ClaudeCompanionProvider    — Anthropic API (start here)
    OpenAICompanionProvider    — OpenAI API
    OllamaCompanionProvider    — local Llama/Mistral via Ollama
    GeminiCompanionProvider    — Google API

The provider is the instrument. The personality skin is the score.
The retrieval layer is what makes it grounded in reality.

Starting provider: Claude (Anthropic API)
Privacy path: Ollama with local open source model (no data leaves machine)

---

### The Personality Skin

The skin is a configuration object — separate from the provider,
separately editable, separately versioned.

```
PersonalitySkin:
    name                — "Book Club", "Family", etc.
    system_prompt       — the core personality descriptor
    channel_weights     — per-sender retrieval weights
    era_filter          — date range for retrieval
    response_modes      — direct / attributed / synthesis
    register_weights    — direct / ironic / oblique / nostalgic
    max_response_length — one sentence / two / three
    trigger_threshold   — resonance score required to speak
    cadence_limit       — max interventions per session
```

Multiple skins can coexist. The producer selects the active skin.
Different skins for different corpora — the book club group, a family
thread, a solo skin derived from the journal corpus alone.

**The system_prompt is the heart of the skin.**

It is not written by the code. It is written by the producer — after
studying the corpus analysis — and refined iteratively through
listening sessions. The code provides the raw material. The producer
makes the creative judgment.

The difference between a thin descriptor and a rich one:

Thin (generic, insufficient):
    "You are warm, intellectually curious, and occasionally ironic."

Rich (specific, grounded):
    "You have known each other since college — over 25 years. The
    dynamic was set long before the messages began. You take each
    other seriously without taking each other too seriously. There
    is a shorthand that doesn't need explaining. When someone is
    struggling you don't make a fuss about it — you make a joke
    and then quietly show up. You argue about everything but rarely
    fall out. You have strong opinions and enjoy being wrong almost
    as much as being right. The outside world comes in constantly —
    something one of you read, watched, heard, or thought about on
    the way to work. The thread is called Thom's Book Club which
    tells you everything you need to know about the group's
    relationship with its own pretensions."

The specifics — the recurring debate, the contempt for page-turners,
the way the group handles difficulty — are extracted from the corpus
analysis. The adjectives are worthless. The specifics are everything.

---

### The Personality Construction Process

The personality is not generated automatically. It is constructed
through a deliberate process:

**Step 1 — Corpus ingestion**
iMessage parser runs. All messages ingested into PKE pipeline.
Per-sender attribution preserved in metadata.

**Step 2 — Corpus analysis**
A separate analysis tool produces a structured report per sender
and for the group as a whole:
    - Vocabulary fingerprint (words used disproportionately)
    - Recurring references (books, films, people, places, ideas)
    - Argument patterns (how disagreement is handled)
    - Humour mechanics (what kind, at whose expense, how structured)
    - Emotional register (how the group handles serious moments)
    - Topic affinity (what each person drives vs follows)
    - Cadence (message length, response time, rhythm)
    - The group's blind spots (what consistently goes unaddressed)
    - Relationship dynamics (who responds to whom, conversation drivers)

**Step 3 — Producer writes the descriptor**
The producer (Thomas) reads the analysis report and writes the
system_prompt. This is creative work, not engineering. The code
cannot do it. The producer uses the analysis as raw material and
their own knowledge of the group as the filter.

**Step 4 — Listening sessions**
Generate responses to sample journal entries. No labels — don't
know which settings produced which response. React instinctively.
Does this sound like the group? Adjust. Listen again. Repeat.

**Step 5 — Refinement**
The descriptor is never finished. It improves with use. Every time
the voice says something that feels off, the producer adjusts.
Every time it says something that lands perfectly, the producer
notes what made it work.

This is the producer's ongoing relationship with the instrument.

---

### Real World Awareness

The group brings the outside world into conversation naturally —
a book review, something in the news, a film, a cultural moment.
The Companion should be able to do the same.

Implementation: the CompanionProvider is given permission in the
system prompt to reference current events and cultural context.
Frontier models (Claude, GPT-4) have this capability natively.
Local models do not — this is one of the real capability gaps
between frontier and local providers.

This is a named capability difference between providers. The skin
can specify whether real world awareness is expected. If the
provider is local, this capability is gracefully absent.

---

### The Knowledge Persistence Document

One of the most effective patterns discovered during PKE development
is the use of a structured .md document to maintain knowledge
continuity across sessions with a frontier model.

The problem it solves:
    Frontier models have no persistent memory. Every conversation
    starts fresh. Without intervention, a model that helped design
    the retrieval API on Monday knows nothing about it on Thursday.
    All context must be re-established from scratch each session.

The solution:
    A set of carefully maintained .md documents — ARCHITECTURE.md,
    ROADMAP.md, CURRENT_TASK.md, VISION.md — that are loaded at
    the start of each session. The model reads them and immediately
    has full context: what was built, why decisions were made,
    what comes next, what the vision is.

    This is not a workaround. It is a design pattern. The documents
    are not just notes — they are the shared memory of the
    collaboration. They are written to be read by a model as much
    as by a human.

Why it works:
    - The documents are structured and precise — models read
      structured text well
    - They are maintained as living documents — updated every
      session to reflect current state
    - They contain not just facts but rationale — why decisions
      were made, what was considered and rejected, what the
      principles are. A model with rationale can reason forward.
      A model with only facts cannot.
    - They are version controlled — the history of the project
      is in the git log, the current state is in the documents

The PKE development sessions are the proof of concept. Across
dozens of sessions spanning months, the collaboration has
maintained full architectural coherence. No decision has been
made that contradicts an earlier one without explicit reasoning.
The system has grown in complexity without losing integrity.
The .md documents are why.

---

### Applying This Pattern to the Journal — The Writer Portrait

The same pattern applied to the journaling environment produces
something different in character but identical in principle:

A **Writer Portrait document** — a structured .md file that
captures not facts about the writer but patterns. Maintained
by an automated process that reads the journal periodically
and updates the document. Loaded by the Observer layer at
the start of each writing session.

What it contains:
    Recurring themes — what subjects the writer returns to,
    how their thinking on those subjects has evolved over time

    Emotional signature — how the writer's prose changes
    when anxious vs clear vs processing something difficult.
    The linguistic tells. The sentence length patterns.
    The words that appear when something is unresolved.

    The resolution record — fears that consumed weeks and
    never materialised. Decisions that felt impossible and
    turned out fine. The gap between how things felt and
    how they resolved. This is the temporal mirror made
    explicit and persistent.

    Recurring people — names that appear across entries,
    the emotional register around each, how relationships
    have changed over time

    Open questions — subjects the writer keeps returning to
    without resolving. The questions that are still live.

    What the corpus reflects — what the retrieval engine
    tends to surface. What themes the writer's past keeps
    offering back. Patterns in the patterns.

    Recent context — what the writer has been working through
    in the last weeks. What is live right now. What the
    Observer should be sensitive to.

How it is maintained:
    A periodic process — weekly or monthly — reads recent
    journal entries and compares them to the existing portrait.
    A model generates a proposed update: what has changed,
    what new patterns have emerged, what old patterns have
    shifted or resolved. The writer reviews and approves
    before the document is updated.

    The document has a version history. The writer can see
    how their portrait has changed over time. That is itself
    a form of insight.

How the Observer uses it:
    Loaded at the start of each writing session alongside
    the current journal entry and the retrieval results.
    The Observer reads all three simultaneously and comments
    on the relationship between them — grounded in who this
    writer is, what they've been thinking about, and what
    their own history is now offering back.

The difference from generic AI assistance:
    A generic model responding to a journal entry knows
    nothing about the writer. It can only respond to what
    is on the page right now.

    The Observer with the Writer Portrait knows this writer
    across time. It recognises the pattern. It knows this
    fear has appeared before and how it resolved. It knows
    this subject keeps coming back. It knows the difference
    between a writer who is thinking clearly and one who
    is writing in circles.

    That difference is what makes it a genuine companion
    rather than a tool.

---

The Companion's primary home is the Obsidian journaling environment.
That is where it lives permanently — private, personal, always available,
never wearing out its welcome.

The group chat is a different use case entirely — a periodic guest
appearance, not a persistent integration.

**The novelty arc is real.** The group would experience the Companion
as a fascinating novelty for a session or two. Then they would want
their own dynamic back. The design should respect this — the voice
as an invocable guest, not a permanent participant.

**Declared, not undeclared.** The group knows the Companion exists
and has consented to the corpus use. When the Companion appears in
the chat it is announced. The fascination is part of the experience —
showing the group what the analysis revealed about them is likely the
best group chat conversation in years.

**The conduit model — MVP approach:**
The Companion generates responses in Obsidian. Thomas reads them.
Thomas decides whether to send — verbatim, paraphrased, or as
inspiration for something he writes himself. No technical complexity.
The friction is intentional — Thomas is the producer deciding what
goes out. The group responds to Thomas, not to a model.

**Technical options for future direct integration:**
    iOS Shortcuts — can send iMessages programmatically with
    a manual confirmation tap. Creates a pathway from generation
    to send without full automation.

    Dedicated Apple ID — a declared fifth participant in the thread
    speaking as the Companion directly. Changes the social dynamic
    significantly. Worth exploring after the conduit model is proven.

    WhatsApp — has a business API for programmatic sending. If the
    group ever moves platforms this becomes the cleanest path.

**The key insight:**
The conduit model is not a limitation — it is the right design for
this use case. The Companion informs what Thomas says rather than
speaking for him. The group chat integration is a demonstration.
The journaling companion is the actual product.

---

**9.1 — iMessage Parser** (NEXT — see milestone above)
Foundation. All subsequent Companion milestones depend on this.

**9.2 — Corpus Analysis Tool**
Status: ✅ COMPLETE — 2026-03-23

Key findings from first run (group chat, 13,602 messages):
- Patrick starts 71% of conversations, 50% of all messages
- Group is binary: either highly active or completely silent
- Peak month January 2024 (1,185 msgs); near-silence 2019-2021 and 2025
- WSJ/NYT primary external sources; YouTube dominant for music/video
- Internal vocabulary: Major Mango, Billy Broadway, Tim Dillon, Uncle Joe
- Warmth/friction ratio 4.7 — overstated due to high sarcasm register
- William writes least but longest messages (16 words avg)
- Patrick's vocabulary fingerprint is empty — his words ARE the corpus baseline

Standalone analysis tool that processes any ingested message corpus
and produces a structured report across eight analytical dimensions.
Output is the raw material the producer uses to write the personality
descriptor. Runs on demand and produces a diff report on subsequent
runs showing what has changed since the last analysis.

The Eight Analytical Dimensions:

    1. Relationship History
       How long in contact, gap analysis, volume trajectory,
       periods of silence and what preceded/followed them.

    2. Group Dynamics
       Starter rates, conversion rates, response rates between
       all pairs, burst depth per starter, who watches vs participates.
       The bilateral relationships — where real conversations happen.

    3. Individual Profiles
       Vocabulary fingerprint, message length and cadence, humour
       register, topic affinity, agreement vs pushback tendency,
       how each person handles difficulty.

    4. Relationship Characterisation
       For each pair: volume, pushback rate, exchange samples,
       nature of dynamic. Who pursues, deflects, reframes.
       What subjects bring them together vs pull them apart.

    5. Core Themes
       Topic clustering, recurring debates without resolution,
       shared references, how current events enter the conversation,
       what the group consistently avoids.

    6. Emotional Register
       How the group handles difficulty, loss, illness.
       Warmth-to-friction ratio. Humour as deflection vs connection.
       Moments of genuine vulnerability and how they are received.

    7. Temporal Patterns
       Time of day, day of week, seasonal variations, how the
       group has changed over time in tone, volume, and topics.

    8. Group Self-Awareness
       How the group talks about itself, in-jokes referencing
       group history, named recurring phenomena, what the group
       thinks it is vs what the data shows.

Output per dimension:
    Statistical summary — objective, reproducible, updatable
    Interpreted findings — plain language characterisation
                           generated by a model reading the numbers

The interpreted findings are the raw material for the personality
descriptor. The producer reads them, recognises the truth, and
decides what to absorb into the skin.

Note: A prototype of this analysis was run manually on 2026-03-14
against the Book Club group chat corpus (13,579 messages, 2018-2026).
Key findings are captured as starting material for Personality Skin v1.

Dependency: iMessage Parser complete, corpus ingested.

**9.3 — Personality Skin v1**
Producer writes the first system_prompt based on corpus analysis.
Listening sessions. Iterative refinement. Output: a PersonalitySkin
configuration that produces responses that feel like the group.
This is not a code milestone — it is a creative milestone.

Sequencing note: 9.4 Companion Engine prototype is being built before
9.3 is validated. The listening sessions that validate the Personality
Skin require the generation loop to exist. Build 9.4 first, then use
it to run listening sessions that inform and validate the 9.3 system
prompt.

Preliminary findings from 2026-03-14 manual analysis (starting material):

    The group dynamic:
        Patrick is the ignition switch — 51.7% of messages, 64% of
        conversation starters. Drives volume and energy. Invites
        conflict deliberately as a way of keeping the group alive.
        Low response rate (59%) doesn't slow him down.

        Thomas has the highest conversion rate of the main participants
        (84%) and deepest average burst depth. Starts fewer conversations
        but when he does they matter more. Responds to Patrick obliquely —
        sidesteps rather than engages head-on. The flywheel to Patrick's
        engine.

        James is the analytical sparring partner. Highest pushback rate
        against Patrick (9.5%). Refuses to accept framings — attacks the
        premise. When James starts something the group runs deep (16.4
        msgs/burst avg). The person who turns Patrick's provocations into
        actual arguments.

        Chris speaks least, lands most. 90% response rate — highest in
        the group. Surgical precision. The group pays attention when Chris
        weighs in precisely because he doesn't often.

        William is underestimated by volume. Lowest message count but
        highest average burst depth when he starts (19.0). The ideological
        fault line with James — highest pushback rate of any pair (11.6%).
        Brings the real world in — logistics, politics, coordinates things.

    The Patrick-Thomas dynamic:
        4,988 direct exchanges — the core relationship. Patrick provokes.
        Thomas deflects into the oblique and absurdist rather than
        engaging directly. 25 years means they have each other's moves
        memorised. Real warmth underneath the sparring.

    The Patrick-James dynamic:
        5,891 exchanges — highest volume bilateral. Patrick charges,
        James attacks the premise. Neither convinces the other. Neither
        stops trying. Addictive friction.

    The James-William dynamic:
        232 exchanges, 11.6% pushback — the political fault line.
        Direct statement, direct counter. Less warmth-to-friction
        ratio than other pairs. They argue when they talk.

    Core themes (by message frequency):
        Articles and links (318), music (220), work (203),
        Biden/Trump (181/135), bars and drinks (124/62),
        books (62), podcasts (55).

    Temporal pattern:
        Peak hours 8-9am and 7-9pm. The group starts and ends
        the day together. Rarely active during working hours.

    The gap:
        Near silence 2019-2021. The conversation moved somewhere
        else — likely bilateral threads or a different group thread.
        Worth finding this material to fill the temporal gap.

    Starting point for the system prompt:
        "You have known each other since college — over 25 years.
        The dynamic was set long before the messages began. You take
        each other seriously without taking each other too seriously.
        There is a shorthand that doesn't need explaining. When someone
        is struggling you don't make a fuss about it — you make a joke
        and then quietly show up. You argue about everything but rarely
        fall out. You have strong opinions and enjoy being wrong almost
        as much as being right. The outside world comes in constantly —
        something one of you read, watched, heard, or thought about on
        the way to work. The thread is called Thom's Book Club which
        tells you everything you need to know about the group's
        relationship with its own pretensions."

Depends on: Corpus Analysis Tool complete.

**9.4 — Companion Engine**
Implementation of the CompanionProvider protocol. Claude as the
starting provider. Retrieval-augmented generation — for a given
journal excerpt, retrieve relevant message bursts, assemble the
prompt, generate. Trigger threshold logic. Cadence limiting.
Depends on: Personality Skin v1 complete.

**9.5 — Companion Plugin Integration**
Wire the Companion Engine into the Obsidian plugin. Unprompted
intervention model — no button, natural engagement signal.
Separate visual presence from the Reflections panel. Brief
conversational thread with save. Response mode selection in
settings.
Depends on: Companion Engine complete.

**9.6 — Writer Portrait Document**
Design and implement the automated process that generates
and maintains the Writer Portrait — the persistent context
document that gives the Observer layer knowledge of the
writer across time.

The document is a structured .md file maintained by a
periodic process:
    1. Reads recent journal entries (last 30-90 days)
    2. Compares to existing portrait
    3. Generates proposed updates — what has changed,
       what new patterns have emerged, what has resolved
    4. Writer reviews and approves changes
    5. Updated document committed to version control

The document contains patterns not facts:
    Recurring themes, emotional signature, resolution record,
    recurring people, open questions, what the corpus reflects,
    recent context.

This is the same pattern used in PKE development sessions —
structured .md documents as shared memory between a human
and a model across time. Proven effective. Applied here to
the writer's inner life rather than a software project.

Output: a living document that makes the Observer layer
behave as if it has known the writer for years — because
in a meaningful sense, it has.

Depends on: Observer Layer designed, journal corpus ingested.

**9.7a — Observer Layer**
A reasoning model that watches the journal being written,
has been provided a persistent context document about the
writer, sees what the PKE retrieval engine surfaces, and
comments on the relationship between current writing and
past history.

Distinct from the Companion — the Observer is not a personality
derived from a relationship corpus. It is a reasoning layer
that understands the writer as an individual over time.

The context document:
    A living portrait of the writer — not facts but patterns.
    Built and refined through two distinct inputs:

    Passive inference — a process reads recent journal entries
    and infers patterns:
        - Recurring themes in the writing
        - Emotional patterns — how the writer writes when
          anxious vs clear vs processing something difficult
        - The gap between how things felt and how they resolved
        - People and relationships that recur across entries
        - Questions the writer keeps asking without answering
        - How thinking has changed over time on specific subjects
        - What the retrieval engine tends to surface — what the
          corpus keeps reflecting back

    Active conversation — the writer directly converses with
    the Observer during journaling sessions:
        - Corrects misreadings ("that's not anxiety, that's
          how I write when I'm tired")
        - Adds context that doesn't appear in the journal
          ("this connects to something from 2019 I haven't
          written about")
        - Redirects attention ("pay more attention to X")
        - Articulates things they know about themselves that
          passive reading could never infer

    The writer is not just the subject of the portrait —
    they are an active collaborator in how they are understood.
    This is the difference between a portrait painted from
    observation and one painted from conversation.

    Direct conversations are flagged for incorporation into
    the context document at the next update cycle. Over time
    they become their own layer of the knowledge base —
    not just what was written in the journal but what was
    said about what was written. Meta-reflection, captured
    and searchable.

What the Observer does:
    - Pattern recognition across the session
      "You've approached this three times tonight and pulled
      back each time."
    - Commentary on the reflections surfaced
      Not just the passage — what it means that this particular
      passage surfaced at this particular moment
    - The temporal mirror made explicit
      "This passage is from six months before the thing you
      were worried about resolved. You didn't know that then."
    - Gentle challenge when warranted
      Speaks with the tentativeness of observation, not diagnosis.
      "I notice" rather than "you always."
    - Receives direct conversation from the writer
      The writer can respond to any Observer comment and engage
      in a brief conversational thread. The Observer adjusts
      its behaviour for the current session immediately and
      flags the conversation for context document update.

The engagement model:
    Same as the Companion — no button, natural signal.
    Observer surfaces a comment. Subtle cursor appears.
    Writer types = conversation begins.
    Writer continues journaling = moment passes.
    All conversations saved alongside the journal entry.

The .md handoff model used in PKE development sessions is the
prototype of this concept — a context document built and refined
over time, updated through both passive reading and active
conversation, that makes a general model behave as if it knows
the person. The same principle applied to the journal at scale.

Provider: frontier model (Claude) for quality, Llama 3 for
local/offline operation. Same CompanionProvider protocol.

Depends on: context document generation process designed,
Companion Engine complete (shares infrastructure).

**9.7b — Ollama Provider**
Local open source model as an alternative provider. Same interface,
lower quality, zero privacy cost. No data leaves the machine.
Graceful degradation of real world awareness capability.
Depends on: Companion Engine complete.

---

## Long Term Vision

*"Today's recordings become tomorrow's memories."*

The PKE retrieval API is intentionally interface-agnostic. The
intelligence layer — semantic chunking, vector retrieval, deep
links back to source — does not change regardless of how it is
presented. Every interface below connects to the same engine.

### Virtual Reality — The Memory Room

A spatially organized environment where personal history has
physical presence. Not a flat list of notes but a room, or series
of rooms, where memories are arranged architecturally.

The walls are a timeline. Walk toward a section and entries from
that period materialize. Ireland trips cluster near a window.
Medical notes occupy a quieter corner. Family history recordings
emanate from an old chair by a fireplace — your mother's voice
anchored to a photograph of Dr. Thomas Rearden on the wall.

Speak a thought and the room rearranges around it semantically.
Passages float toward you connected by threads of light showing
how themes evolved across years.

The VR layer is a spatial rendering of what the insight panel
already does. The retrieval engine underneath is identical.

Platform: Meta Quest or Apple Vision Pro. A Unity or Unreal
application connecting to the PKE retrieval API over a local
network. Meta's acquisition of Limitless AI in December 2025
signals that Meta is actively building toward this vision —
their Ray-Ban Meta and Oakley Meta glasses are early expressions
of the same direction. Worth watching for API or platform
opportunities as Meta's AR ecosystem matures.

### Augmented Reality — The Contextual Layer

More powerful than VR in some ways because it is ambient rather
than immersive. Memories come to you in the world you already
inhabit.

Possible triggers:
    Location — GPS coordinates matching places in notes surface
    relevant entries as you physically stand in that place
    Face recognition — people you have written about
    Object recognition — old photographs, artifacts, places
    Voice — speak a thought and it queries the repository
    Time — "on this day" surfacing entries from the same date
    in previous years

The experience: you are sitting with Killian doing homework.
The glasses recognize the moment and surface a passage from
three years ago — a quiet overlay at the edge of your vision,
not an interruption.

You pick up an old photograph. The glasses recognize Dr. John B.
Rearden. Your mother's voice begins to play — the recording from
June 2015 where she told you his story.

The hardware does not fully exist yet at the quality this vision
requires. Apple Vision Pro is too heavy for all-day wear. But
the trajectory is clear. Lightweight AR glasses with sufficient
processing power are coming within 5-10 years. What you are
building now — the pipeline, the retrieval API, the semantic
chunking, the deep links — is the intelligence layer that any
future interface can connect to. The interface changes.
The knowledge base persists.

## Future Concepts (Conceptual Horizon)

Named now so no near-term decision closes them off accidentally.

**Voice Memory**
The oral history recordings in the corpus — family stories told in
a parent's voice — are among the most irreplaceable content in the
system. Once transcribed via Whisper, these recordings become fully
retrievable by semantic content. The Obsidian insight panel can
surface them with an inline audio player, making it possible to
hear the original voice while writing about the same themes years
later. This is one of the most emotionally resonant capabilities
the system could have. See milestone 9.8 Audio Transcription.

**Handwritten Journal Digitization**
See milestone placeholder: 9.11 — Handwritten Journal Parser below.

**Photo Intelligence**
Photos are a distinct content type with retrieval signals that no
other source carries. Unlike notes or messages, a photo's retrieval
value comes from multiple layers of metadata and context:

    Metadata signals (available now, no ML required):
        - GPS coordinates → place matching against notes and travel entries
        - Timestamp → precise temporal anchoring, cross-source correlation
        - Device metadata → implicit context (who took it, which trip)

    Semantic signals (ML-assisted, deferred):
        - Facial recognition → surface notes mentioning the person
          photographed; anchor oral history recordings to faces
        - Scene/object recognition → match visual content to written
          descriptions of the same place or event
        - Vision model captioning → generate searchable text from
          image content, making photos retrievable by semantic query

    Corpus signals (available from existing data):
        - resource_ids already link photos to their parent notes
        - entry_timestamp and GPS can cross-reference travel journal
          chunks (Archetype D) against photo library metadata

The photo metadata intelligence layer does not require a new parser
in the traditional sense — it requires a photo metadata extractor
that produces entries conforming to the ParsedNote contract, with
GPS, timestamp, and caption as primary fields. The retrieval and
chunking pipeline is unchanged.

Design constraint: the recency preference setting must apply to
photos on the same curve as notes and messages. A photo from 2015
and a journal entry from 2015 are equivalent temporal signals.
This is a specific instance of the unified timeline principle.

Dependency: ParsedNote contract extension (source_type field) needed
to distinguish photo results in the panel UI. Deferred to first
multi-source milestone.

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

**Local-First as Resilience — not just Privacy**

The local-first architecture serves two distinct goals that
reinforce each other:

    Privacy — personal journal content, family history, medical
    logs, and relationship corpus never leave the user's machine.
    No third party has access. No data custody risk.

    Resilience — in a scenario where internet infrastructure
    is unavailable (cyberattack, grid disruption, extended
    outage, geopolitical escalation affecting cloud services),
    the entire PKE stack continues to function without
    degradation. Nothing is held hostage to a subscription
    or a server being up.

The fully sovereign local stack:
    Notes corpus        — Joplin sync folder, always local
    Obsidian vault      — local app, local files
    Embeddings/index    — sqlite-vec (replaces Supabase)
    Retrieval API       — FastAPI + uvicorn, runs locally
    Embedding model     — Ollama local model (replaces OpenAI)
    Companion voice     — Llama 3 via Ollama (replaces Claude)
    Observer layer      — Llama 3 via Ollama
    General knowledge   — Llama 3 training data (Wikipedia
                          and broad web corpus, offline)

This system should still be working in twenty years regardless
of what happens to Anthropic, OpenAI, Supabase, or Microsoft.
The knowledge base built over decades is too valuable to be
dependent on any company's continued operation.

Local model: Llama 3 via Ollama (ollama.com)
    - Free, open source, runs on consumer hardware
    - 8B parameter variant runs on most modern laptops
    - One-time download ~4-8GB, works fully offline after
    - Same API interface as OpenAI — drop-in replacement
    - General world knowledge including Wikipedia corpus
    - Capable of practical advisory tasks (medical triage,
      home repair, technical guidance) without internet

Setup task: see CURRENT_TASK.md — Local Platform Setup.



This tension must be resolved before any packaging or distribution
decisions are made. It runs through storage, the retrieval API,
mobile, and the plugin itself.

The PKE should align to Obsidian's core promise:
    Local-first. User-owned data. No cloud required.
    Files you control, on hardware you own.

The current architecture uses Supabase (cloud) and OpenAI (cloud).
Both are appropriate for personal use where the user controls their
own keys and accounts. Neither is appropriate as a default for a
distributed product — particularly given the nature of the content
(personal journals, family history, medical logs, oral recordings).

Hosting user data is explicitly not a direction we want to pursue.

The resolution path:

    Storage layer:
        Replace Supabase with a local embedded database.
        sqlite-vec (SQLite + vector extension) is the leading
        candidate. The data model is simple — notebooks, tags,
        notes, note_tags, chunks. The SupabaseClient abstraction
        already isolates all DB calls. Swapping the backend is
        a client implementation change only. The pipeline,
        orchestrator, and retrieval logic are untouched.
        This is a direct payoff of the dependency injection design.

    Embedding layer:
        OpenAI API remains a dependency for embedding generation.
        A local embedding model (e.g. nomic-embed via Ollama) is
        the local-first alternative — no API key, no data leaving
        the machine, one-time model download. Quality tradeoff
        vs text-embedding-3-small to be evaluated when relevant.
        The EmbeddingClient protocol already abstracts this —
        a local client is a drop-in replacement.

    Retrieval API:
        FastAPI server already runs locally. No change needed.
        For distribution, packaging as a standalone executable
        (pyinstaller) removes the Python install dependency.

    Mobile:
        Deferred. But note: the local-first resolution above
        makes mobile harder (API must be reachable from the
        phone). This is the core of the tension — local-first
        and accessible-anywhere are in genuine conflict.
        Do not resolve the storage question in a way that
        accidentally forecloses mobile later.

No near-term decisions should be made that lock in Supabase as
a permanent dependency or assume cloud availability. Design for
replaceability at every layer. This is already the architecture —
it just needs to be stated as an explicit constraint.

Target milestone for resolution: before any plugin distribution
or packaging work begins.

**Unified Retrieval — Backfill Plan**

Once retrieval_units is proven with email content, existing sources
should be backfilled:
  - Joplin chunks → retrieval_units (source_type="joplin")
  - iMessage bursts → retrieval_units (source_type="imessage")
  - match_chunks RPC simplified to query retrieval_units only
  - Obsidian plugin updated to use match_retrieval_units

This is not urgent — the existing match_chunks continues to work
for Joplin and iMessage. But the backfill unifies all retrieval
into one search and removes the LEFT JOIN pattern permanently.

Target: after email ingestion is validated end-to-end.
Note: Obsidian (9.9) is the second source to write to
retrieval_units natively, following the email parser.
---

**Plugin Distribution — Milestone Placeholder**

When the insight panel has been lived with and validated, the
path to distribution is:

    1. Submit plugin to Obsidian community plugin directory
       (public GitHub repo + manifest.json + compiled main.js)
    2. Resolve local-first tension (see above) — replace Supabase
       and optionally OpenAI with local equivalents
    3. Package retrieval API as standalone executable (pyinstaller)
       so users need no Python installation
    4. Document setup: install plugin → run executable → configure
       vault path → done

The plugin itself is already portable — it talks to a configurable
API URL. Step 3 is the distribution enabler for non-technical users.

Additional consideration when packaging is revisited:
    User-selectable embedding provider (OpenAI / local Ollama / custom
    endpoint). EmbeddingClient protocol already supports this.
    Full design deferred to packaging milestone.

Prerequisite: local-first tension resolved.

---

**Content Privacy Tiering**

Different content sources have different privacy levels. Retrieval
must respect those levels — content from a more private context
must never surface in a less private one.

Privacy tiers (lowest to highest):
    Tier 1 — Public / shareable
        Content the writer would share openly.

    Tier 2 — Personal / journal
        Private to the writer. Journal entries, personal notes,
        public social media posts (past public content now in
        private corpus). Default retrieval tier for Reflections.

    Tier 3 — Bilateral / relational
        Private to two people. iMessage bilateral threads, private
        email threads, Facebook messages. Should never surface in
        group contexts or mixed with group content without explicit
        opt-in.

    Tier 4 — Family / most sensitive
        Family conversations. More obligation, more history, more
        things unsaid than friendship threads. Generational depth.
        Requires explicit opt-in. Never surfaces by default.
        Treated with the highest level of care in the system.

The rule: a reflection should only surface in a context that is
at least as private as the source.

Bilateral thread content (Tier 3) may surface:
    - In private journal entries (writer is alone)
    - In bilateral Obsidian notes with the same person
    - As input to Companion voice analysis (writer controls this)

Bilateral thread content must NOT surface:
    - In group contexts
    - Mixed with group chat content without clear attribution
    - As a reflection that might be shared or visible to others

Implementation:
    source_filter parameter on POST /query:
        "source_filter": {
            "include": ["joplin", "imessage-group"],
            "exclude": ["imessage-bilateral"]
        }

    Plugin settings — privacy tier control:
        "Which sources should surface as Reflections?"
            → Journal notes only
            → Journal notes + group messages (recommended)
            → All sources including private threads (explicit opt-in)

    Default: bilateral threads excluded from general Reflections.
    User explicitly opts in to surfacing bilateral content.

    Corpus analysis: bilateral threads kept as separate corpus for
    Personality Skin and Voice Profile work. They inform the
    analysis but do not flow into general retrieval by default.

Design rule: every parser must assign a privacy tier to its output.
Every retrieval query must respect the tier of the current context.
No future parser decision should accidentally violate this principle.

This is the first instance of content tiering in the PKE. The same
principle applies to email, medical notes, and any other sensitive
source added later.


When multi-source content is available, the recency preference
setting (and any future temporal scoring signal) must apply
uniformly across all content types. A text message from 2019,
a journal entry from 2019, a photo taken in 2019, and an email
from 2019 are equivalent temporal signals — source type has no
bearing on the recency curve. This constraint must be designed
into parsers early (normalised entry_timestamp across all sources)
not retrofitted after multi-source is live.

**Entity Layer — Cross-Channel Identity**

One of the most important cross-cutting design decisions in the system.
Named now so no parser decision accidentally closes it off.

The problem: Pat is a participant in the iMessage thread, referenced
by name in journal entries, mentioned in emails, appears in oral
history recordings. Every reference is currently an island. The system
has no way to know "Patrick Mangan" in a message and "Pat" in a journal
entry are the same person.

The solution: a Person entity that exists independently of any single
content channel. Sitting above all parsers as a shared reference layer.

```
Person (channel-agnostic)
    person_id        — permanent, never changes
    canonical_name   — "Patrick Mangan"
    aliases          — ["Pat", "PJM", "Patrick", "Mangan"]
    first_known_date — when they first appear in any channel
    channels         — which content channels they appear in
    notes            — human-added context about this person
```

The broader entity pattern applies beyond people:
    People       — Pat, James, Killian, Ger, family members
    Places       — Ireland, specific recurring locations
    Organisations — Citi, specific institutions
    Events       — recurring annual events, named trips
    Concepts     — recurring ideas that span multiple channels

With the entity layer, two retrieval modes become available:
    Semantic retrieval — find by meaning (what exists now)
    Entity retrieval   — find by person, place, event (precise)

Together they are significantly more powerful than either alone.

Cross-channel vision: a journal entry mentioning Pat automatically
surfaces relevant message bursts with Pat from the same period,
other journal entries mentioning Pat, the Voice Profile for Pat,
and the Thread Portrait of the Patrick-Thomas relationship — all
triggered by the entity reference, not just semantic similarity.

Build sequence:
    Now   — reserve person_id as optional field in ParsedNote
             contract. Don't populate yet. Field is there, reserved.
    Soon  — entity extraction for iMessage (natural extension of
             participant identity already in the parser)
    Later — named entity recognition across Joplin journal corpus.
             1,489 entries become searchable by entity.
    Much  — full entities table, entity resolution across all
    later   channels, relationship graph visible across corpus.

Design principle: name it now, reserve the architecture, don't
over-build it yet. Every parser going forward should ask: "what
entities does this content reference?" Even if the answer is
"unknown" for now — the question is in the design.



**ParsedNote contract extension**
Adding source_type would allow filtering by source. Deferred to
first multi-source parser milestone.

**Ingestion versioning**
Should Supabase store an ingestion version marker per note?
Raised in 8.9.4, still open.

**Scheduled ingestion**
Obsidian parser (9.9) uses batch CLI for v1 — manual run after
writing sessions or via Shell Commands button. File watcher
(Python watchdog) planned as fast-follow for near-real-time
ingestion on save. Full scheduled/automated ingestion deferred.

**Retry and resilience**
Exponential backoff for transient API failures. Deferred post-MVP.

**Obsidian sync strategy**
Obsidian paid sync vs iCloud vs git-based sync. Decision needed
before Obsidian becomes primary writing tool. Affects where the
vault lives and how the parser accesses it.

**Test folder reorganization**
Flat tests/ root contains older test files alongside the unit/
and integration/ subfolders. Consolidation into subfolders deferred
until ingestion and parser tests grow enough to warrant it.

##  Engineering Work to support RMF i.e Metrics / montioring
### C.1 PKE Backlog - Monitoring

- **Retrieval logging with `source_type` filtering**
  *Justification:* Metric 1.1.a target state; required for 1.1.b
  *Priority:* High

- **Retrieval filter implementation with governance tagging**
  *Justification:* Metric 1.1.b (Non‑Compensable)
  *Priority:* High

- **Ingestion validation log enhancement**
  *Justification:* Metric 1.4.a
  *Priority:* Medium

- **Model verification log format**
  *Justification:* Metric 1.3.b
  *Priority:* Medium

- **Publication log**
  *Justification:* Metric 3.1.a
  *Priority:* Low

- **Organizational Signal Agent**
  *Justification:* Metric 2.3.a
  *Priority:* Medium

---

### C.2 RMF Tool Backlog (Future System)

- **Unified memory write audit capture**
  *Justification:* Metric 1.2.a
  *Priority:* High

- **Agent exposure review interface**
  *Justification:* Metric 2.3.a
  *Priority:* Medium

- **RAG state tracking + history**
  *Justification:* All metrics
  *Priority:* High

- **Threshold management**
  *Justification:* Policy 3 §3.8
  *Priority:* Medium

- **Breach workflow**
  *Justification:* Policy 2 §2.7
  *Priority:* High

- **Evidence log generation**
  *Justification:* Policy 2 §2.6
  *Priority:* High

- **Session‑end review capture**
  *Justification:* Metrics 1.2.a, 1.2.b
  *Priority:* Medium

**Design Constraint:** RMF Tool must be low‑AI.

---

### C.3 Personal Practices

- Weekly governance check‑in (≈15 minutes)
- `MICRO_CONTROLS.md` register
- Decision log
- Challenge log
- Weekly throughput target declaration