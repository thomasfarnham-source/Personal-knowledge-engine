# Personal Knowledge Engine — System Architecture

This document defines the architecture, contracts, and sequencing of the
Personal Knowledge Engine (PKE). It is the authoritative reference for all
system-level reasoning, design decisions, and future development. All AI
tools must treat this document as the source of truth.

---

## 1. System Overview

The Personal Knowledge Engine is a deterministic, two-stage ingestion
pipeline that converts personal notes into a structured, queryable
knowledge base backed by Supabase and embeddings.

The canonical workflow is:

    pke parse run
    pke ingest run --dry-run
    pke ingest run

The system is built around:
- deterministic, reproducible ingestion
- explicit contracts between stages
- pluggable parsers
- dependency-injected clients
- testability and isolation
- clean separation of concerns

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
tags, notebooks, and relationships.

Entry point:   pke/cli/ingest.py
Orchestrator:  pke/ingestion/orchestrator.py

Steps:
- Extract and upsert notebooks
- Extract and upsert tags
- Upsert notes with embeddings
- Link notes ↔ tags

The orchestrator is deterministic and idempotent.

---

## 3. Parser History and Current State

### Markdown Export Parser (Deprecated)

The original parser targeted Joplin's Markdown export format. This
approach failed because Joplin produced incomplete exports:
- missing frontmatter
- missing titles
- missing tags
- missing notebook names
- missing timestamps

This parser (joplin_markdown.py) remains in the repo for reference
but is no longer used and must never be modified or referenced
in active code paths.

### Sync Folder Parser (Canonical Source)

File: pke/parsers/joplin_sync_parser.py

The Joplin sync folder contains:
- .md files for notes, notebooks, tags, and relationships
- consistent metadata blocks
- reliable timestamps
- stable UUIDs

This is the correct and only source of truth.

parse_cli.py is wired to this parser. Any future changes to Stage 1
must go through joplin_sync_parser.py, not joplin_markdown.py.

---

## 4. ParsedNote Contract

Every parsed note must contain exactly these fields:

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

Rules:
- No missing fields
- No extra fields
- No None values
- Empty string or empty list for missing metadata

This contract must not change.

---

## 5. Joplin Sync Folder Format

All data lives in .md files.

Type Map (Confirmed):
- type_ 1 → Note
- type_ 2 → Notebook
- type_ 5 → Tag
- type_ 6 → Note-tag relationship

Note Structure (type_: 1):
    [first line = title]
    [blank line]
    [body content]
    [metadata block]
    type_: 1

Notebook Structure (type_: 2):
    [name]
    [metadata block]
    type_: 2

Tag Structure (type_: 5):
    [name]
    [metadata block]
    type_: 5

Relationship Structure (type_: 6):
    note_id: <uuid>
    tag_id: <uuid>
    type_: 6

---

## 6. Three-Pass Parser Architecture

The parser must follow this exact sequencing:

Pass 1 — Load and Classify
- Read every .md file
- Parse title, body, metadata
- Classify by type_
- Produce raw dictionaries

Pass 2 — Build Lookup Maps
- notebook_map: {notebook_id → notebook_name}
- tag_map: {tag_id → tag_name}
- note_tag_map: {note_id → [tag_ids]}

Pass 3 — Enrich and Normalize Notes
- Resolve parent_id → notebook name
- Resolve tag IDs → tag names
- Extract resource links
- Normalize field names
- Build final ParsedNote objects
- Sort by id for determinism

---

## 7. Determinism Requirements

- Running the parser twice on the same folder must produce identical output.
- Notes must be sorted by id.
- No shared mutable state across passes.
- Each pass must construct new dicts/lists.
- No randomization or nondeterministic ordering.
- Running ingestion twice must produce identical Supabase state.

---

## 8. Missing Metadata Rules

- Missing notebook → ""
- Missing tags → []
- Missing timestamps → ""
- Empty body → "" (parser preserves; orchestrator skips at ingest time)
- Encrypted notes (encryption_applied: 1) → skip with warning

---

## 9. Parser vs Orchestrator — Intentional Contract Divergence

The parser and orchestrator have different responsibilities with
respect to empty-body notes. This is intentional and must not change.

Parser (Stage 1):
- Preserves all notes including empty-body notes
- Never drops or filters notes (except encrypted)
- Produces a lossless representation of the sync folder

Orchestrator (Stage 2):
- Skips empty-body notes at ingest time
- Counts them as notes_skipped in IngestionReport
- Does not upsert them to Supabase

Reason: empty-body notes produce no embedding, no semantic value,
and no search utility. The parser must be lossless; the orchestrator
must be meaningful.

---

## 10. Supabase Integration

Supabase stores:
- notebooks
- tags
- notes (with embeddings)
- note↔tag relationships

Ingestion table reset order (when a full reset is required):

    TRUNCATE TABLE note_tags, conflicts, resources, notes, notebooks, tags;

All tables must be truncated in a single statement due to FK constraints.

Tables never truncated by the ingestion pipeline:
- ingestion_log
- documents
- deleted_notes

All DB operations go through SupabaseClient, which supports:
- real Supabase client
- DummyClient for dry-run
- mock clients for tests

The parser must never call Supabase.

---

## 11. Testing Philosophy

- deterministic ingestion
- dependency injection
- no network calls in unit tests
- fixtures for parsed notes
- E2E tests for parse → ingest

The sync-folder parser has a dedicated test suite:
    tests/test_joplin_sync_parser.py

---

## 12. Collaboration Workflow

Development follows a three-step loop:
- Design (Thomas + Claude)
- Implement (VS Code Copilot)
- Review (Thomas + Claude)

All decisions are recorded in CURRENT_TASK.md.
ARCHITECTURE.md is the authoritative reference and must be updated
whenever a structural decision changes.

---

## 13. Current Objective

Complete milestone 8.9.4:
1. Fix parse_cli.py to wire joplin_sync_parser (prerequisite)
2. Run pke parse run against the Joplin sync folder
3. Validate with pke ingest run --dry-run
4. Run pke ingest run against the clean Supabase baseline
5. Confirm determinism by running ingestion twice