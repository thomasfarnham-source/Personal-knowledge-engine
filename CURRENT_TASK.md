# CURRENT_TASK.md
## Milestone 8.9.4 — Deterministic Ingestion Baseline — COMPLETED 2026-03-03

---

## Status: COMPLETE

All acceptance criteria met. Supabase contains a clean, deterministic
baseline of 1489 notes, 16 notebooks, 57 tags, and 212 relationships.
Pipeline has been validated as idempotent across two full runs.

---

## What Was Built

A clean, correct, deterministic ingestion baseline in Supabase using
the new sync-folder parser. This establishes the foundation for
milestone 8.9.5 (embeddings).

---

## What Was Fixed

### 1. parse_cli.py — wrong parser wired (critical bug)
- Was importing deprecated `joplin_markdown.parse_joplin_export`
- Fixed to import canonical `joplin_sync_parser.parse_sync_folder`
- Docstrings updated to reflect sync-folder terminology
- All 40 tests passed after fix

### 2. ingest.py — real SDK client constructed in dry-run mode (bug)
- `--dry-run` was constructing a real Supabase SDK client
- Caused orchestrator dry-run path to call real Supabase methods
- Fixed: dry-run now uses DummyClient, real mode uses SDK client
- Credentials check moved inside real mode branch only

---

## Design Decisions Made

- The new sync-folder parser is canonical and produces correct
  ParsedNote objects.
- The previous ingestion used an early sync parser that was incomplete
  and non-deterministic.
- Determinism requires a clean baseline; ingestion tables were truncated
  before re-ingestion.
- Only ingestion tables were truncated (ingestion_log, documents,
  deleted_notes preserved).
- Ingestion proceeds in deterministic order:
  notebooks → tags → notes → relationships.
- Empty-body notes are preserved by the parser but skipped by the
  orchestrator. This is intentional and must not change.
- Deterministic placeholder embeddings are written in 8.9.4.
  Real embeddings will be generated in 8.9.5.
- A transient Supabase 502 error caused 1 note to fail on the first
  run. The pipeline handled it non-fatally and recovered on the
  second run. No data corruption occurred.

---

## Artifacts Produced

- scripts/reset_ingestion_tables.sql — truncation script for future resets
- scripts/inspect_schema.sql — diagnostic schema queries
- pke/artifacts/parsed/parsed_notes.json — 1493 parsed notes (gitignored)

---

## Final Ingestion Results

### Run 1
- notes_processed: 1493
- notes_inserted: 1488
- notes_updated: 0
- notes_skipped: 4
- tags_inserted: 57
- relationships_created: 212
- failures: 1 (transient 502 — note efc8ebcc8c114b5b856871d30b065df3)

### Run 2 (determinism confirmation + failure recovery)
- notes_processed: 1493
- notes_inserted: 0
- notes_updated: 1489
- notes_skipped: 4
- tags_inserted: 57
- relationships_created: 212
- failures: []

---

## Supabase State (confirmed)
- notes: 1489
- notebooks: 16
- tags: 57
- note_tags: 212

---

## Guardrails and Architecture Updates

- ARCHITECTURE.md updated:
  - parse_cli.py must wire to joplin_sync_parser (explicit)
  - Parser vs orchestrator contract divergence documented
  - Supabase truncation order documented
  - Section 9 added: intentional empty-body note handling
- AI Coding Guidelines updated:
  - Commentary Standards section added
  - Existing file style must be matched on all modifications

---

## Known Performance Issue (post-MVP)

Every ingestion run makes 2 Supabase round trips per note (SELECT +
UPSERT) regardless of how many notes actually changed. This can be
optimized using Postgres native upsert detection (xmax = 0) to reduce
round trips by ~50%. Deferred to a post-MVP performance milestone.

---

## Constraints Met

- ✅ joplin_markdown.py not modified
- ✅ joplin_sync_parser.py not modified
- ✅ Orchestrator contract not modified
- ✅ Supabase schema not modified
- ✅ No embeddings generated (placeholder only)
- ✅ No new dependencies introduced
- ✅ No notes skipped except empty-body (4) and encrypted
- ✅ ParsedNote structure unchanged
- ✅ Ingestion is deterministic

---

## Open Questions (deferred)

- Should we add a Supabase ingestion version marker for future migrations?
- Should ingestion logs be persisted to a table for auditability?
- Should we snapshot parsed_notes.json for reproducibility?
- Should retry with exponential backoff be added for transient failures?
- Should ingestion be scheduled (cron, change detection, cloud job)?

---

## Next Milestone: 8.9.5 — Embeddings

Goal: Replace deterministic placeholder embeddings with real semantic
embeddings using a configured embedding provider.

Prerequisites:
- Choose embedding provider (OpenAI, Cohere, HuggingFace)
- Configure API key in .env
- Wire real EmbeddingClient into SupabaseClient
- Re-ingest all notes to generate real embeddings
- Validate embedding quality