# CURRENT_TASK.md
## Milestone 8.9.7 — Retrieval API

Last updated: 2026-03-08 21:48 EST

---

## Status: COMPLETE ✅

Branch: feat/8.9.7-retrieval-api
Committed and pushed.

---

## What Was Delivered

**SupabaseClient extended — four new methods**
- fetch_unembedded_chunks(batch_size) — fetches chunks where embedding IS NULL
- update_chunk_embedding(chunk_id, embedding) — writes embedding back to chunk row
- match_chunks(query_embedding, match_count, filter_notebook) — pgvector RPC search
- match_notes(query_embedding, match_count, filter_notebook) — pgvector RPC fallback

**SQL migration scripts**
- scripts/add_match_functions.sql — registers match_chunks and match_notes
  as Postgres RPC functions using pgvector cosine distance (<=> operator)

**pke/cli/embed_chunks.py**
- Standalone CLI backfill command
- Walks all chunks where embedding IS NULL in batches of 100
- Generates embeddings via OpenAI text-embedding-3-small
- Safe to re-run — only processes unembedded chunks
- Result: 866 chunks embedded

**pke/api/ — FastAPI application**
- pke/api/main.py — app entry point, dependency wiring at startup
- pke/api/routes/query.py — POST /query endpoint
- pke/api/models/query.py — QueryRequest, QueryResult, QueryResponse
  Pydantic models

**pke/retrieval/retriever.py**
- Hybrid retrieval logic
- Step 1: embed query via OpenAI
- Step 2: search chunks via match_chunks RPC
- Step 3: search notes via match_notes RPC (fallback)
- Step 4: merge and rank by similarity score
- Step 5: return top N QueryResult objects
- _score() hook isolated for future signals (recency, archetype,
  timestamp confidence)

**pke/embedding/openai_client.py — updated**
- tiktoken added for accurate token counting
- Truncates to 8191 tokens using actual tokenizer before embedding
- Fixes 17 notes that previously failed with token limit errors
- tiktoken added to pyproject.toml dependencies

**Full ingest validated**
- 1489 notes updated, 4 skipped (empty body), 0 failures
- 866 chunks with real OpenAI embeddings
- Smoke test confirmed: POST /query returning real semantic results

**Smoke test result — query: "Ireland family history"**
- Ireland 2019 pt 1 — similarity 0.482 — chunk result
- Notes from 2012 Ireland trip — similarity 0.444 — chunk result
- Untitled Ireland trip note — similarity 0.435 — chunk result
  (36 resource IDs, entry_timestamp 2015-06-05)

All three results chunk-level. Hybrid strategy working correctly.

### Design Decisions Made in 8.9.7
- tiktoken used for token counting — character-based truncation
  unreliable for corpus with markdown, special characters, Irish text
- Scoring hook (_score) isolated in retriever for future signals
- Dependencies wired once at FastAPI startup — not per-request
- match_notes uses NOT EXISTS to enforce no overlap with chunk results
- Deep link infrastructure complete — note_id, chunk_index, char_start,
  resource_ids all returned per result

---

## Previous Milestone: 8.9.6 — COMPLETE ✅

Completed 2026-03-07. All acceptance criteria met.
See git history for full details.

---

## Next Milestone: 8.9.8 — Obsidian Insight Plugin

Branch to cut: feat/8.9.8-obsidian-plugin

### What We Are Building

A custom Obsidian plugin (TypeScript) that connects the writing surface
to the PKE retrieval API. The primary consumer-facing expression of the
system.

### Acceptance Criteria

- [ ] Plugin watches active note for changes
- [ ] After short debounce, sends current paragraph to POST /query
- [ ] Renders top 3-5 results in a side panel
- [ ] Each result displays: date, note title, relevant passage (raw text)
- [ ] Click note title → opens source note in Obsidian
- [ ] Click passage → opens source note at exact paragraph (char_start)
- [ ] Audio chunks → inline play button for original recording
- [ ] Image chunks → opens note at photo location
- [ ] Results optionally appendable to current entry as dated annotation
- [ ] No AI-generated summaries — raw content only
- [ ] Plugin communicates with PKE retrieval API running locally

### Remaining from 8.9.7 (carry forward)

- [ ] Write tests:
    - tests/unit/test_retriever.py — retrieval logic with mocked Supabase
    - tests/test_retrieval_api.py — endpoint tests with FastAPI TestClient
    - tests/unit/test_embed_chunks.py — backfill CLI unit tests

### Tech Stack for 8.9.8

- TypeScript — Obsidian plugin language
- Obsidian Plugin API — plugin scaffolding and UI
- PKE Retrieval API (8.9.7) — must be running locally or hosted

### Writing Surface Setup (same milestone)

- Obsidian vault configured as primary writing tool
- Light templates by note type installed
- Journal, medical/reference, book/idea templates defined
- Migration plan for Joplin notes into Obsidian vault

---

## Next Session Start Point

1. Cut branch: git checkout -b feat/8.9.8-obsidian-plugin
2. Write deferred tests from 8.9.7 (retriever, API endpoint, embed_chunks)
3. Begin Obsidian plugin design
4. Update CURRENT_TASK.md timestamp (ask Thomas for actual time)
