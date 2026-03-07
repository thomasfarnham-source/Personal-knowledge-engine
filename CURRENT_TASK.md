# CURRENT_TASK.md
## Milestone 8.9.5 — Real Embeddings + Chunk Schema Foundation

---

## Status: IN PROGRESS

---

## What We Are Building

Replace deterministic placeholder embeddings with real semantic embeddings
using OpenAI's text-embedding-3-small model. Add the chunks table to
Supabase as an empty schema foundation for milestone 8.9.6 chunking.
No chunking logic is implemented in this milestone.

---

## Context From 8.9.4

- Supabase contains a clean baseline: 1489 notes, 16 notebooks,
  57 tags, 212 relationships
- All notes currently have deterministic placeholder embeddings
- Pipeline is validated as idempotent
- The ingestion pipeline is the authoritative path for all embedding writes

---

## Design Decisions Made

### Embedding Provider: OpenAI text-embedding-3-small
- Model: text-embedding-3-small
- Output dimensions: 1536
- Input token limit: 8191 (~6000 words)
- Notes exceeding token limit: truncate to fit, log a warning
- API key stored in .env as OPENAI_API_KEY

### EmbeddingClient: New OpenAI implementation
- New file: pke/embedding/openai_client.py
- Implements existing EmbeddingClient protocol
- Constructor accepts model name and API key (injected, not from env)
- Single public method: embed(text: str) -> list[float]
- Raises typed exception on API failure (not silent)
- ingest.py loads OPENAI_API_KEY from env and injects into client

### Chunk Schema: Added now, populated in 8.9.6
- New Supabase table: chunks
- Created via migration script this milestone
- Orchestrator does NOT write to chunks in 8.9.5
- Schema includes section_title and entry_timestamp fields
  in anticipation of archetype-aware chunking in 8.9.6

### Re-ingestion Strategy
- All 1489 notes re-ingested to replace placeholder embeddings
- Ingestion is idempotent (upsert); re-running is safe
- No truncation required — existing notes updated in place
- Run sequence: pke ingest run --dry-run → pke ingest run

---

## Chunks Table Schema

```sql
CREATE TABLE chunks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id          UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    chunk_index      INTEGER NOT NULL,
    chunk_text       TEXT NOT NULL,
    embedding        vector(1536),
    char_start       INTEGER NOT NULL,
    char_end         INTEGER NOT NULL,
    section_title    TEXT,           -- heading above this chunk if any
    entry_timestamp  TEXT,           -- inline timestamp from entry if any
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (note_id, chunk_index)
);
```

Migration script: scripts/add_chunks_table.sql

---

## Function Signatures Agreed

### pke/embedding/openai_client.py

```python
class OpenAIEmbeddingClient:
    """
    EmbeddingClient implementation backed by OpenAI text-embedding-3-small.
    Injects API key and model name via constructor for testability.
    """
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small"
    ) -> None: ...

    def embed(self, text: str) -> list[float]: ...
```

### pke/cli/ingest.py (changes only)

```python
# Load OPENAI_API_KEY from env
# Construct OpenAIEmbeddingClient
# Inject into SupabaseClient constructor
# All other CLI behaviour unchanged
# --dry-run still uses DummyClient with no OpenAI calls
```

---

## Acceptance Criteria

- [ ] pke/embedding/openai_client.py exists and implements EmbeddingClient
- [ ] OpenAIEmbeddingClient.embed() returns list of 1536 floats
- [ ] ingest.py reads OPENAI_API_KEY from env and injects correctly
- [ ] --dry-run uses DummyClient; no OpenAI calls made
- [ ] All 1489 notes re-ingested with real embeddings (notes_updated: 1489)
- [ ] Notes exceeding 8191 tokens truncated with warning logged
- [ ] chunks table created in Supabase via migration script
- [ ] chunks table includes section_title and entry_timestamp columns
- [ ] No chunking logic added anywhere
- [ ] All existing tests pass
- [ ] New unit tests for OpenAIEmbeddingClient with mocked responses
- [ ] .env.example updated with OPENAI_API_KEY= entry

---

## Constraints

- Do NOT modify joplin_sync_parser.py
- Do NOT modify orchestrator.py contracts
- Do NOT modify ParsedNote structure
- Do NOT generate embeddings inside the parser
- Do NOT write to the chunks table in this milestone
- Do NOT add chunking logic anywhere in this milestone
- Do NOT commit .env

---

## Test Cases (tests/test_openai_embedding_client.py)

1. test_embed_returns_correct_dimension
   → mock OpenAI response, assert len == 1536

2. test_embed_raises_on_api_failure
   → mock API error, assert typed exception raised

3. test_embed_sends_correct_model
   → assert request uses text-embedding-3-small

4. test_dry_run_does_not_call_openai
   → DummyClient path, assert no OpenAI calls made

---

## Open Questions (deferred)

- Should embedding failures be non-fatal (skip note) or fatal (abort)?
  → Recommend non-fatal, consistent with 8.9.4 transient failure handling
- Should we store embedding model name alongside each note for future
  migration tracking?
- Retry strategy for transient OpenAI failures → deferred post-MVP

---

## Next Milestone: 8.9.6 — Chunking for Long Notes

Goal: Archetype-aware chunking for notes above a length threshold.
Populate the chunks table. Handle Archetype A (fragmented journal),
Archetype B (structured journal), and Archetype C (reference log)
correctly.
CURRENT_TASK.md
Milestone 8.9.5 — Real Embeddings + Chunk Schema Foundation

Status: IN PROGRESS — IMPLEMENTATION COMPLETE, VALIDATION PENDING

What We Are Building
Replace deterministic placeholder embeddings with real semantic embeddings
using OpenAI's text-embedding-3-small model. Add the chunks table to
Supabase as an empty schema foundation for milestone 8.9.6 chunking.
No chunking logic is implemented in this milestone.

Context From 8.9.4

Supabase contains a clean baseline: 1489 notes, 16 notebooks,
57 tags, 212 relationships
All notes currently have deterministic placeholder embeddings
Pipeline is validated as idempotent
The ingestion pipeline is the authoritative path for all embedding writes


Design Decisions Made
Embedding Provider: OpenAI text-embedding-3-small

Model: text-embedding-3-small
Output dimensions: 1536
Input token limit: 8191 (~6000 words)
Notes exceeding token limit: truncate to fit, log a warning
API key stored in .env as OPENAI_API_KEY

EmbeddingClient: New OpenAI implementation

New file: pke/embedding/openai_client.py
Implements existing EmbeddingClient protocol
Constructor accepts model name and API key (injected, not from env)
Single public method: embed(text: str) -> list[float]
Raises typed exception on API failure (not silent)
ingest.py loads OPENAI_API_KEY from env and injects into client

Chunk Schema: Added now, populated in 8.9.6

New Supabase table: chunks
Created via migration script this milestone
Orchestrator does NOT write to chunks in 8.9.5
Schema includes section_title and entry_timestamp fields
in anticipation of archetype-aware chunking in 8.9.6

Re-ingestion Strategy

All 1489 notes re-ingested to replace placeholder embeddings
Ingestion is idempotent (upsert); re-running is safe
No truncation required — existing notes updated in place
Run sequence: pke ingest run --dry-run → pke ingest run


Chunks Table Schema
sqlCREATE TABLE chunks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id          UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    chunk_index      INTEGER NOT NULL,
    chunk_text       TEXT NOT NULL,
    embedding        vector(1536),
    char_start       INTEGER NOT NULL,
    char_end         INTEGER NOT NULL,
    section_title    TEXT,           -- heading above this chunk if any
    entry_timestamp  TEXT,           -- inline timestamp from entry if any
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (note_id, chunk_index)
);
Migration script: scripts/add_chunks_table.sql

Function Signatures Agreed
pke/embedding/openai_client.py
pythonclass OpenAIEmbeddingClient:
    """
    EmbeddingClient implementation backed by OpenAI text-embedding-3-small.
    Injects API key and model name via constructor for testability.
    """
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small"
    ) -> None: ...

    def embed(self, text: str) -> list[float]: ...
pke/cli/ingest.py (changes only)
python# Load OPENAI_API_KEY from env
# Construct OpenAIEmbeddingClient
# Inject into SupabaseClient constructor
# All other CLI behaviour unchanged
# --dry-run still uses DummyClient with no OpenAI calls

Progress — End of Session 2026-03-05
Completed This Session

 OpenAI account created, API key generated, added to .env
 chunks table created in Supabase via migration script (confirmed success)
 pgvector confirmed enabled in Supabase
 pke/embedding/openai_client.py created and reviewed
 generate() alias added to OpenAIEmbeddingClient for orchestrator
compatibility (orchestrator calls .generate(), not .embed())
 ingest.py updated to wire OpenAIEmbeddingClient (not yet reviewed
in full — paste ingest.py for review at start of next session)

Discovered This Session

pke/embedding/providers/ folder exists with openai_provider.py,
cohere_provider.py, huggingface_provider.py — all superseded, safe
to delete once tests pass
pke/embedding/embedding_client.py is still actively used by
supabase_client.py, notes_cli.py, and orchestrator dry-run path —
do NOT delete yet
pke/ingestion.py (root level, Evernote-era) has no active imports —
safe to delete, deferred to post-validation cleanup
pke/wrapped_supabase_client.py and pke/entity_resolution.py exist
at root level — not yet investigated, review next session

Next Session Start Point

Paste ingest.py here for review before running anything
Run validation commands in order:

flake8 pke
mypy pke
pytest
pke ingest run --dry-run


If all pass, run pke ingest run (real embeddings, 1489 notes)
Confirm in Supabase: all notes have real embeddings, chunks table empty
Write Prompt 3 (tests) and run it
Clean up dead code (providers folder, root ingestion.py)
Mark 8.9.5 complete and set up 8.9.6

Acceptance Criteria

 pke/embedding/openai_client.py exists and implements EmbeddingClient
 OpenAIEmbeddingClient.embed() returns list of 1536 floats
 OpenAIEmbeddingClient.generate() alias works correctly
 ingest.py reads OPENAI_API_KEY from env and injects correctly
 --dry-run uses DummyClient; no OpenAI calls made
 All 1489 notes re-ingested with real embeddings (notes_updated: 1489)
 Notes exceeding 8191 tokens truncated with warning logged
 chunks table created in Supabase via migration script ✅
 chunks table includes section_title and entry_timestamp columns ✅
 No chunking logic added anywhere
 All existing tests pass
 New unit tests for OpenAIEmbeddingClient with mocked responses
 .env.example updated with OPENAI_API_KEY= entry


Constraints

Do NOT modify joplin_sync_parser.py
Do NOT modify orchestrator.py contracts
Do NOT modify ParsedNote structure
Do NOT generate embeddings inside the parser
Do NOT write to the chunks table in this milestone
Do NOT add chunking logic anywhere in this milestone
Do NOT commit .env


Test Cases (tests/test_openai_embedding_client.py)

test_embed_returns_correct_dimension
→ mock OpenAI response, assert len == 1536
test_embed_raises_on_api_failure
→ mock API error, assert typed exception raised
test_embed_sends_correct_model
→ assert request uses text-embedding-3-small
test_dry_run_does_not_call_openai
→ DummyClient path, assert no OpenAI calls made


Open Questions (deferred)

Should embedding failures be non-fatal (skip note) or fatal (abort)?
→ Recommend non-fatal, consistent with 8.9.4 transient failure handling
Should we store embedding model name alongside each note for future
migration tracking?
Retry strategy for transient OpenAI failures → deferred post-MVP


Next Milestone: 8.9.6 — Chunking for Long Notes
Goal: Archetype-aware chunking for notes above a length threshold.
Populate the chunks table. Handle Archetype A (fragmented journal),
Archetype B (structured journal), and Archetype C (reference log)
correctly.
Prerequisites:CURRENT_TASK.md
Milestone 8.9.5 — Real Embeddings + Chunk Schema Foundation

Status: IN PROGRESS — IMPLEMENTATION COMPLETE, VALIDATION PENDING

What We Are Building
Replace deterministic placeholder embeddings with real semantic embeddings
using OpenAI's text-embedding-3-small model. Add the chunks table to
Supabase as an empty schema foundation for milestone 8.9.6 chunking.
No chunking logic is implemented in this milestone.

Context From 8.9.4

Supabase contains a clean baseline: 1489 notes, 16 notebooks,
57 tags, 212 relationships
All notes currently have deterministic placeholder embeddings
Pipeline is validated as idempotent
The ingestion pipeline is the authoritative path for all embedding writes


Design Decisions Made
Embedding Provider: OpenAI text-embedding-3-small

Model: text-embedding-3-small
Output dimensions: 1536
Input token limit: 8191 (~6000 words)
Notes exceeding token limit: truncate to fit, log a warning
API key stored in .env as OPENAI_API_KEY

EmbeddingClient: New OpenAI implementation

New file: pke/embedding/openai_client.py
Implements existing EmbeddingClient protocol
Constructor accepts model name and API key (injected, not from env)
Single public method: embed(text: str) -> list[float]
Raises typed exception on API failure (not silent)
ingest.py loads OPENAI_API_KEY from env and injects into client

Chunk Schema: Added now, populated in 8.9.6

New Supabase table: chunks
Created via migration script this milestone
Orchestrator does NOT write to chunks in 8.9.5
Schema includes section_title and entry_timestamp fields
in anticipation of archetype-aware chunking in 8.9.6

Re-ingestion Strategy

All 1489 notes re-ingested to replace placeholder embeddings
Ingestion is idempotent (upsert); re-running is safe
No truncation required — existing notes updated in place
Run sequence: pke ingest run --dry-run → pke ingest run


Chunks Table Schema
sqlCREATE TABLE chunks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id          UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    chunk_index      INTEGER NOT NULL,
    chunk_text       TEXT NOT NULL,
    embedding        vector(1536),
    char_start       INTEGER NOT NULL,
    char_end         INTEGER NOT NULL,
    section_title    TEXT,           -- heading above this chunk if any
    entry_timestamp  TEXT,           -- inline timestamp from entry if any
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (note_id, chunk_index)
);
Migration script: scripts/add_chunks_table.sql

Function Signatures Agreed
pke/embedding/openai_client.py
pythonclass OpenAIEmbeddingClient:
    """
    EmbeddingClient implementation backed by OpenAI text-embedding-3-small.
    Injects API key and model name via constructor for testability.
    """
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small"
    ) -> None: ...

    def embed(self, text: str) -> list[float]: ...
pke/cli/ingest.py (changes only)
python# Load OPENAI_API_KEY from env
# Construct OpenAIEmbeddingClient
# Inject into SupabaseClient constructor
# All other CLI behaviour unchanged
# --dry-run still uses DummyClient with no OpenAI calls

Progress — End of Session 2026-03-05
Completed This Session

 OpenAI account created, API key generated, added to .env
 chunks table created in Supabase via migration script (confirmed success)
 pgvector confirmed enabled in Supabase
 pke/embedding/openai_client.py created and reviewed
 generate() alias added to OpenAIEmbeddingClient for orchestrator
compatibility (orchestrator calls .generate(), not .embed())
 ingest.py updated to wire OpenAIEmbeddingClient (not yet reviewed
in full — paste ingest.py for review at start of next session)

Discovered This Session

pke/embedding/providers/ folder exists with openai_provider.py,
cohere_provider.py, huggingface_provider.py — all superseded, safe
to delete once tests pass
pke/embedding/embedding_client.py is still actively used by
supabase_client.py, notes_cli.py, and orchestrator dry-run path —
do NOT delete yet
pke/ingestion.py (root level, Evernote-era) has no active imports —
safe to delete, deferred to post-validation cleanup
pke/wrapped_supabase_client.py and pke/entity_resolution.py exist
at root level — not yet investigated, review next session

Next Session Start Point

Paste ingest.py here for review before running anything
Run validation commands in order:

flake8 pke
mypy pke
pytest
pke ingest run --dry-run


If all pass, run pke ingest run (real embeddings, 1489 notes)
Confirm in Supabase: all notes have real embeddings, chunks table empty
Write Prompt 3 (tests) and run it
Clean up dead code (providers folder, root ingestion.py)
Mark 8.9.5 complete and set up 8.9.6

Acceptance Criteria

 pke/embedding/openai_client.py exists and implements EmbeddingClient
 OpenAIEmbeddingClient.embed() returns list of 1536 floats
 OpenAIEmbeddingClient.generate() alias works correctly
 ingest.py reads OPENAI_API_KEY from env and injects correctly
 --dry-run uses DummyClient; no OpenAI calls made
 All 1489 notes re-ingested with real embeddings (notes_updated: 1489)
 Notes exceeding 8191 tokens truncated with warning logged
 chunks table created in Supabase via migration script ✅
 chunks table includes section_title and entry_timestamp columns ✅
 No chunking logic added anywhere
 All existing tests pass
 New unit tests for OpenAIEmbeddingClient with mocked responses
 .env.example updated with OPENAI_API_KEY= entry


Constraints

Do NOT modify joplin_sync_parser.py
Do NOT modify orchestrator.py contracts
Do NOT modify ParsedNote structure
Do NOT generate embeddings inside the parser
Do NOT write to the chunks table in this milestone
Do NOT add chunking logic anywhere in this milestone
Do NOT commit .env


Test Cases (tests/test_openai_embedding_client.py)

test_embed_returns_correct_dimension
→ mock OpenAI response, assert len == 1536
test_embed_raises_on_api_failure
→ mock API error, assert typed exception raised
test_embed_sends_correct_model
→ assert request uses text-embedding-3-small
test_dry_run_does_not_call_openai
→ DummyClient path, assert no OpenAI calls made


Open Questions (deferred)

Should embedding failures be non-fatal (skip note) or fatal (abort)?
→ Recommend non-fatal, consistent with 8.9.4 transient failure handling
Should we store embedding model name alongside each note for future
migration tracking?
Retry strategy for transient OpenAI failures → deferred post-MVP


Next Milestone: 8.9.6 — Chunking for Long Notes
Goal: Archetype-aware chunking for notes above a length threshold.
Populate the chunks table. Handle Archetype A (fragmented journal),
Archetype B (structured journal), and Archetype C (reference log)
correctly.
Prerequisites:

8.9.5 complete (real embeddings, chunks table exists)
10-15 most important historical notes re-read and lightly
restructured (Current State headers, normalized dates)
These restructured notes used as primary chunker test cases
Chunking strategy finalized (date-stamp primary, template
sections secondary, undated headers as reference chunks)

8.9.5 complete (real embeddings, chunks table exists)
10-15 most important historical notes re-read and lightly
restructured (Current State headers, normalized dates)
These restructured notes used as primary chunker test cases
Chunking strategy finalized (date-stamp primary, template
sections secondary, undated headers as reference chunks)
Prerequisites:
- 8.9.5 complete (real embeddings, chunks table exists)
- 10-15 most important historical notes re-read and lightly
  restructured (Current State headers, normalized dates)
- These restructured notes used as primary chunker test cases
- Chunking strategy finalized (date-stamp primary, template
  sections secondary, undated headers as reference chunks)