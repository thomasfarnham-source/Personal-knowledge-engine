# CLAUDE.md — Personal Knowledge Engine

This file orients AI tools to the PKE project. Read it before
making any changes. Treat ARCHITECTURE.md as the authoritative
reference for all system-level decisions.

---

## What This Project Is

A personal intelligence layer that ingests journal notes and
message threads into a queryable knowledge base, surfaces
semantically relevant passages in real time while journaling
in Obsidian, and (in future milestones) introduces a generative
companion voice derived from real friendship corpora.

---

## Repos

Pipeline and API:  thomasfarnham-source/Personal-knowledge-engine
Obsidian plugin:   thomasfarnham-source/pke-obsidian-plugin
VS Code workspace: C:\Users\thoma\Documents\dev\PKE.code-workspace

---

## How to Run Tests

```powershell
pytest                          # full suite
pytest tests/unit/ -v           # unit tests only
pytest tests/unit/test_X.py -v  # specific file
```

All 464 tests must pass before any commit.

## Code Quality — run before every commit

```powershell
black .
flake8
mypy .
pytest
```

The pre-commit hook runs these automatically on `git commit`.
Use `--no-verify` only when committing documentation-only changes.

---

## Pipeline Commands

```powershell
pke parse run                          # parse Joplin notes → JSON
pke ingest run --dry-run               # preview ingestion
pke ingest run                         # ingest Joplin notes → Supabase
pke ingest-imessage file "path.csv"    # ingest single iMessage CSV
pke ingest-imessage file "path.csv" --dry-run
pke ingest-imessage dir "path/"        # ingest all CSVs in directory
uvicorn pke.api.main:app --reload      # start retrieval API
```

---

## Architecture — Critical Rules

**Never touch these:**
- `pke/parsers/joplin_markdown.py` — deprecated, must not be modified
- `pke/parsers/joplin_sync_parser.py` — canonical parser, stable

**Parser contract:**
- Every parser produces a ParsedNote dict
- See Section 4 of ARCHITECTURE.md for the full contract
- person_ids must always be present (None until entity layer built)
- privacy_tier must always be assigned

**Database:**
- The database is an index, never an archive
- Source files are the source of truth
- Re-ingestion is always safe — all operations are idempotent
- Parser must never call Supabase

**Determinism:**
- Same input must always produce same output
- IDs are SHA-256 hashes of stable content — never random for
  parser output

**Privacy:**
- Every parser must assign privacy_tier to its output
- Group threads → tier 2, bilateral threads → tier 3
- Family threads → tier 4 (when built)
- The Group Voice Boundary Rule: a voice operating in an external
  channel may only draw from content that originated in that channel

---

## Key Files

```
ARCHITECTURE.md          — authoritative system reference
ROADMAP.md               — milestone sequence and vision
CURRENT_TASK.md          — current milestone status and next steps
WRITER_PORTRAIT_TEMPLATE.md — Observer Layer context document

pke/parsers/
    joplin_sync_parser.py    — Joplin parser (canonical)
    imessage_parser.py       — iMessage parser (milestone 9.1)

pke/ingestion/
    orchestrator.py          — Joplin ingestion pipeline
    imessage_ingestor.py     — iMessage ingestion pipeline

pke/cli/
    main.py                  — CLI entry point (Typer)
    ingest.py                — pke ingest commands
    parse_cli.py             — pke parse commands
    ingest_imessage.py       — pke ingest-imessage commands

pke/api/
    main.py                  — FastAPI retrieval API
    routes/query.py          — POST /query endpoint

pke/retrieval/
    retriever.py             — hybrid retrieval logic

pke/supabase_client.py       — database client wrapper

scripts/
    add_chunks_table.sql     — chunks table schema
    add_match_functions.sql  — pgvector RPC functions
    add_imessage_tables.sql  — iMessage tables + updated RPCs

tests/
    unit/
        test_imessage_parser.py    — 50 tests
        test_imessage_ingestor.py  — 27 tests
        test_retriever.py          — 25 tests
        test_retrieval_api.py      — 22 tests
        test_embed_chunks.py       — 16 tests
```

---

## Current Milestone

**9.1 — iMessage Parser** — IN PROGRESS

Remaining:
- Run first real ingestion (group chat CSV)
- Run ingestion for Patrick bilateral thread
- Run embed_chunks backfill for iMessage bursts
- Verify bursts surface in Obsidian Reflections panel
- Write PR and close milestone

Next milestone: 9.2 — Corpus Analysis Tool

---

## iMessage Export Locations

```
C:\Users\thoma\OneDrive\Documents\Iphone Exports\
    Messages - James Root & William Renahan & Chris Zic-1.csv  (group)
    Messages - Patrick Mangan.csv                              (bilateral)
    Messages - Patrick Mangan & James Root & William Re.csv    (sub-group)
    Messages - Patrick Mangan & William Renahan & Glenn.csv    (sub-group)
```

---

## Supabase Tables

Existing: notebooks, tags, notes, note_tags, chunks, resources,
          conflicts, deleted_notes, ingestion_log, documents

Added milestone 9.1: imessage_threads, imessage_participants,
                     imessage_messages, imessage_bursts

chunks table extended: source_type, source_id, privacy_tier columns

---

## Collaboration Pattern

Design decisions → CURRENT_TASK.md
Architecture changes → ARCHITECTURE.md
Vision and milestones → ROADMAP.md

Development loop: Design (Thomas + Claude) → Implement → Review
Thomas is the producer and decision-maker.
Claude is the architect and reviewer.
VS Code Copilot assists with implementation.
