# CURRENT_TASK.md
## Milestone 8.9.6 — Chunking for Long Notes

Last updated: 2026-03-07 08:32 EST


---

## Status: PLANNED — NOT STARTED

---

## Previous Milestone: 8.9.5 — COMPLETE ✅

Completed 2026-03-06. All acceptance criteria met.

### What Was Delivered
- pke/embedding/openai_client.py — OpenAI text-embedding-3-small client
- generate() alias added for orchestrator compatibility
- ingest.py updated to wire OpenAIEmbeddingClient
- tests/test_openai_embedding_client.py — 4 unit tests
- chunks table created in Supabase with resource_ids TEXT[] column
- All 1489 notes re-ingested with real OpenAI embeddings (confirmed)
- Branch feat/8.9.5-embeddings published and PR submitted

### Schema Changes Made in 8.9.5
- chunks table created via migration script
- resource_ids TEXT[] DEFAULT '{}' added via ALTER TABLE

### Dead Code Identified (cleanup deferred)
- pke/embedding/providers/ — entire folder, superseded
- pke/ingestion.py (root level) — Evernote-era, no active imports
- pke/entity_resolution.py (root level) — no active imports
- tests/integration/test_embedding_client_mock.py — placeholder only
- tests/unit/test_embedding_wrapper.py — placeholder only

### Quality of Life Item (deferred from 8.9.5)
- Add progress counter to orchestrator (e.g. "Processed 150/1489...")
- Add logging to file alongside stdout output
- Add as first task in 8.9.6 or standalone commit

---

## What We Are Building

Archetype-aware chunking for notes above a length threshold.
Populate the chunks table with semantically meaningful chunks.
Handle all five note archetypes correctly.

---

## Note Archetypes — Chunking Requirements

### Archetype A — Fragmented Journal
- Primary split: date stamps (regex, tolerates typo variants)
- Merge entries under ~100 tokens with neighbors
- High noise tolerance

### Archetype B — Structured Journal
- Primary split: date stamps
- Secondary split: template section headers for long entries
- Preserve retrospective annotations with their original entry

### Archetype C — Reference / Medical Log
- Undated opening section → own reference chunk
- Dated log → split on date stamps
- Embedded sub-tables → keep intact

### Archetype D — Travel Journal
- Primary split: flexible day marker detection
    Day N, Day N Title, standalone day names,
    day names in prose, narrative transitions
- Pre-trip planning block → own reference chunk
- Timestamp strategy (three tiers):
    Explicit date in text → entry_timestamp directly
    Day name / Day N → "calculated: YYYY-MM-DD" from created_at
    No marker → entry_timestamp null
- Image handling (two formats):
    Markdown: ![alt](:/resource_id)
    HTML:     <img src=":/resource_id" .../>
- Audio handling: [filename.m4a](:/resource_id)
- Broken placeholders stripped silently:
    {picture)  (Picture)  (picture)  image
- Resource IDs → chunks.resource_ids array
- note_type: travel flag in chunk metadata
- Fallback: paragraph boundaries where day detection fails

### Archetype E — Oral History / Conversation Notes
- Embed whole note if below ~1000 char threshold
- If above threshold: chunk on audio file boundaries
- Timestamp: extracted from audio filename
    Format: YYYY-MM-DD HH:MM:SS (most reliable in corpus)
- Audio resources flagged as resource_type: audio in metadata

---

## General Chunking Rules

- Apply chunking selectively: notes above ~1000 characters only
- Below threshold: note embedding serves as the chunk embedding
- Minimum chunk: ~100 tokens
- Maximum chunk: ~500 tokens with 1-2 sentence overlap at boundaries
- Date stamp regex must tolerate typo variants
- Chunking module: pke/chunking/chunker.py (new file)

---

## Chunks Table Schema (current)

```sql
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
```

entry_timestamp format:
    Explicit:   "2015-09-08"
    Calculated: "calculated: 2014-08-04"
    None:       NULL

---

## Pre-Work Before Implementation

None required. Proceed directly to chunker implementation.

Note restructuring (adding Current State headers, normalizing dates,
adding retrospective annotations) is deferred. It is a quality lever
to pull later — not a prerequisite. The chunker must handle messy
real-world content from the start. When notes are eventually
restructured in Obsidian, re-running pke ingest will automatically
re-chunk and re-embed the updated content.

Test fixtures will use the real corpus note samples already analyzed
during archetype design (travel notes, journal samples, oral history).

---

## Design Decisions To Make

- Exact day marker regex patterns for Archetype D
- Threshold for "long enough to chunk" (proposed: ~1000 chars)
- Overlap strategy at chunk boundaries
- How to handle notes that span multiple archetypes
- Whether to detect archetype automatically or require manual tagging

---

## Acceptance Criteria

- [ ] pke/chunking/chunker.py exists with archetype detection
- [ ] Archetype A notes chunked correctly on date stamps
- [ ] Archetype B notes chunked with template section awareness
- [ ] Archetype C undated opening section as reference chunk
- [ ] Archetype D day marker detection working for all observed formats
- [ ] Archetype D calculated timestamps stored with "calculated: " prefix
- [ ] Archetype D resource IDs extracted into resource_ids array
- [ ] Archetype D broken placeholders stripped silently
- [ ] Archetype E audio timestamps extracted from filenames
- [ ] Notes below threshold not chunked
- [ ] chunks table populated for all qualifying notes
- [ ] All chunk embeddings generated via OpenAI
- [ ] tests/test_chunker.py passing with fixtures for all archetypes
- [ ] Existing tests still passing

---

## Constraints

- Do NOT modify joplin_sync_parser.py
- Do NOT modify ParsedNote structure
- Do NOT modify the orchestrator embedding logic
- Do NOT write to notes table in the chunking module
- Do NOT commit .env

---

## Next Session Start Point

1. Cut branch: git checkout -b feat/8.9.6-chunking
2. Review dead code list from 8.9.5 — clean up before chunker work
3. Add progress counter and file logging to orchestrator
4. Begin chunker design with Archetype A as first implementation
5. Use real corpus notes as test fixtures
