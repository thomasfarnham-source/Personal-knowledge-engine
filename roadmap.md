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
  and semantically indexed (see milestone 9.x Audio Transcription)

---

## Content Channels (Current and Planned)

| Channel              | Status      | Notes                                   |
|----------------------|-------------|------------------------------------------|
| Joplin notes         | ✅ Complete  | Sync-folder parser, canonical Stage 1   |
| Obsidian notes       | 🔵 Planned  | Future primary writing surface          |
| iMessage threads     | 🔵 Planned  | Specific contacts or groups             |
| Yahoo Mail           | 🔵 Planned  | Select senders                          |
| Handwritten journals | 🔵 Future   | Photo → vision model → PKE parser       |
| Others (TBD)         | 🔵 Open     | Calendar, bookmarks, documents          |

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

### 🔵 8.9.8 — Obsidian Insight Plugin
**Status: PLANNED**

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
    until Joplin → Obsidian migration is complete (milestone 9.x).
    Expected dependency, not a bug.

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

### 🔵 9.x — Audio Transcription and Playback
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

### 🔵 9.x — Obsidian Parser + Migration
**Status: PLANNED**

Add Obsidian vault as ingestion source. Migrate historical Joplin
corpus into Obsidian. Retire Joplin as active writing surface.

#### Parser
- New parser: pke/parsers/obsidian_parser.py
- Source: local Obsidian vault directory (Markdown files)
- Frontmatter support: YAML frontmatter natively supported
- Tags extracted from both inline (#tag) and frontmatter
- Backlinks extractable as relationships
- ParsedNote contract unchanged — pipeline is source-agnostic

#### Migration Strategy (Joplin → Obsidian)
The migration follows a strict sequence with a validation gate:

Phase 1 — Build the Obsidian parser first
    Continue using Joplin pipeline as-is during development.
    New notes can be written in Obsidian immediately.
    Both sources can be ingested in parallel during transition.

Phase 2 — Migrate Joplin corpus into Obsidian vault
    Use Joplin's built-in Markdown export or Obsidian export plugin.
    Handles attachments and internal links.
    Validation gate: compare note count, check resource files,
    spot-check content against original Joplin source.
    Do NOT proceed until validation passes.

Phase 3 — Re-ingest from Obsidian
    Point pipeline at Obsidian vault. Full re-ingest.
    Validate: note count and embedding count match previous baseline.
    Retire Joplin as active source once confirmed.

Phase 4 — Restructure notes gradually (ongoing)
    Restructure notes opportunistically in Obsidian over time.
    Each restructure → re-ingest → improved retrieval quality.
    This is a quality lever, not a prerequisite.

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

---

### 🔵 9.x — Photo Intelligence
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

### 🔵 9.x — Handwritten Journal Parser
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
the system could have. See milestone 9.x Audio Transcription.

**Handwritten Journal Digitization**
See milestone placeholder: 9.x — Handwritten Journal Parser below.

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

**⚠ Critical Unresolved Dependency — Local-First vs Cloud Access Tension**

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

**Unified timeline principle**
When multi-source content is available, the recency preference
setting (and any future temporal scoring signal) must apply
uniformly across all content types. A text message from 2019,
a journal entry from 2019, a photo taken in 2019, and an email
from 2019 are equivalent temporal signals — source type has no
bearing on the recency curve. This constraint must be designed
into parsers early (normalised entry_timestamp across all sources)
not retrofitted after multi-source is live.

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

**Test folder reorganization**
Flat tests/ root contains older test files alongside the unit/
and integration/ subfolders. Consolidation into subfolders deferred
until ingestion and parser tests grow enough to warrant it.
