Personal Knowledge Engine — System Architecture
This document defines the architecture, contracts, and sequencing of the Personal Knowledge Engine (PKE). It is the authoritative reference for all system-level reasoning, design decisions, and future development. All AI tools must treat this document as the source of truth.

1. System Overview
The Personal Knowledge Engine is a deterministic, two-stage ingestion pipeline that converts personal notes into a structured, queryable knowledge base backed by Supabase and embeddings.
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

2. Pipeline Architecture
Stage 1 — Parse
Goal: Convert raw note sources into a structured, lossless JSON artifact.
Output file:
pke/artifacts/parsed/parsed_notes.json

This file is the only input to Stage 2.
Stage 2 — Ingest
Goal: Transform parsed notes into Supabase entities with embeddings, tags, notebooks, and relationships.
Steps:
- Extract and upsert tags
- Resolve notebook names → Supabase IDs
- Upsert notes with embeddings
- Link notes ↔ tags
- Link notes ↔ notebooks
The orchestrator is deterministic and idempotent.

3. Parser History and Current State
Markdown Export Parser (Deprecated)
The original parser targeted Joplin’s Markdown export format. This approach failed because Joplin produced incomplete exports:
- missing frontmatter
- missing titles
- missing tags
- missing notebook names
- missing timestamps
This parser remains in the repo for reference but is no longer used.
Sync Folder Parser (Canonical Source)
The Joplin sync folder contains:
- .md files for notes, notebooks, tags, and relationships
- consistent metadata blocks
- reliable timestamps
- stable UUIDs
This is the correct source of truth.
Current Task
Implement a new sync-folder parser (joplin_sync_parser.py) that produces complete ParsedNote objects matching the ingestion contract.

4. ParsedNote Contract
Every parsed note must contain exactly these fields:
{
    "id": str,
    "title": str,
    "body": str,
    "notebook": str,          # resolved notebook name or ""
    "tags": list[str],        # resolved tag names
    "created_at": str,        # ISO timestamp or ""
    "updated_at": str,        # ISO timestamp or ""
    "metadata": dict,         # all remaining metadata fields
    "source_file": str,       # absolute path
    "resource_links": list[str],  # extracted resource IDs
}

Rules:
- No missing fields
- No extra fields
- No None values
- Empty string or empty list for missing metadata
This contract must not change.

5. Joplin Sync Folder Format
All data lives in .md files.
Type Map (Confirmed)
|  |  |
|  |  |
|  |  |
|  |  |
|  |  |
|  |  |
|  |  |


Note Structure (type_: 1)
[first line = title]
[blank line]
[body content]
[metadata block]
type_: 1


Notebook Structure (type_: 2)
[name]
[metadata block]
type_: 2


Tag Structure (type_: 5)
[name]
[metadata block]
type_: 5


Relationship Structure (type_: 6) — Confirmed
note_id: <uuid>
tag_id: <uuid>
type_: 6


This enables deterministic construction of:
note_tag_map[note_id] = [tag_ids...]



6. Three-Pass Parser Architecture
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

7. Determinism Requirements
- Running the parser twice on the same folder must produce identical output.
- Notes must be sorted by id.
- No shared mutable state across passes.
- Each pass must construct new dicts/lists.
- No randomization or nondeterministic ordering.

8. Missing Metadata Rules
- Missing notebook → ""
- Missing tags → []
- Missing timestamps → ""
- Empty body → ""
- Encrypted notes (encryption_applied: 1) → skip with warning

9. Supabase Integration
Supabase stores:
- notebooks
- tags
- notes
- embeddings
- note↔tag relationships
- note↔notebook relationships
All DB operations go through SupabaseClient, which supports:
- real Supabase client
- DummyClient for dry-run
- mock clients for tests
The parser must not call Supabase.

10. Testing Philosophy
- deterministic ingestion
- dependency injection
- no network calls in unit tests
- fixtures for parsed notes
- E2E tests for parse → ingest
The sync-folder parser must include a dedicated test suite:
tests/test_joplin_sync_parser.py


11. Collaboration Workflow
Development follows a three-step loop:
- Design (Thomas + Claude)
- Implement (VS Code Copilot)
- Review (Thomas + Claude)
All decisions are recorded in CURRENT_TASK.md.

12. Current Objective
Implement the new sync-folder parser using the design specification in CURRENT_TASK.md.
After implementation, return the code to Claude for system-level review.