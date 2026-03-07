# Personal Knowledge Engine — AI Coding Guidelines

## AI-Assisted Development Workflow

This project uses a structured three-step collaboration model between
**Thomas** (owner), **Claude** (system-level reasoning), and
**VS Code Copilot** (file-level implementation).

### Roles

- **Thomas**: Owner and final authority. Defines problems, approves all
  architectural decisions and code.
- **Claude (External)**: System-level reasoning. Defines module boundaries,
  contracts, schemas, failure modes, and architectural coherence.
  Does *not* write code.
- **VS Code Copilot**: File-level implementation. Writes functions, generates
  tests, refactors modules, updates imports. Does *not* make architectural
  decisions.

### Three-Step Development Loop

1. **System-Level Design** (Thomas + Claude)
   - Output: `CURRENT_TASK.md` specification
   - Includes: function signatures, contracts, acceptance criteria,
     constraints, test cases, open questions
   - This is the handoff to VS Code Copilot

2. **File-Level Implementation** (VS Code Copilot)
   - Uses the specification to write code, tests, and refactors
   - Thomas reviews before proceeding

3. **System-Level Review** (Thomas + Claude)
   - Checklist: signatures match? determinism preserved? failure modes
     explicit? tests present? no hidden coupling? aligned with constraints?
   - Revise if needed and repeat

### The CURRENT_TASK.md Handoff Artifact

This file bridges sessions, tools, and architectural decisions:

```markdown
## Current Task
[what we are building right now]

## Design Decisions Made
[key choices and why]

## Function Signatures Agreed
[exact signatures]

## Acceptance Criteria
[what "done" looks like]

## Constraints
[what not to do]

## Test Cases
[tests that must pass]

## Open Questions
[unresolved items]
```

Update this file at the end of every session; paste it at the start of
the next to carry context forward.

### Guiding Principles

- Thomas owns every decision. AI proposes; Thomas approves.
- Architecture is explicit, not implicit.
- Contracts are written before code is written.
- Tests define correctness.
- Review enforces determinism and clarity.

---

## Project Overview

**Personal Knowledge Engine** is a personal intelligence layer built
around a reflective writing experience. The system has two faces:

**The pipeline** — a deterministic, two-stage ingestion system that
parses personal notes and other content channels into a structured,
queryable knowledge base backed by Supabase and semantic embeddings.

**The writing environment** — an Obsidian-based writing surface with
a custom plugin (TypeScript) that queries the PKE retrieval API in
real time as the user writes, surfacing semantically relevant passages
from personal history in a live insight panel alongside the writing
surface.

The core user experience: while writing a journal entry, the system
quietly surfaces diary reflections from the past that connect to what
the user is thinking about right now. The writing process belongs to
the user. The system provides material for reflection, not conclusions.

The canonical pipeline workflow is:

    pke parse run
    pke ingest run --dry-run
    pke ingest run

---

## Architecture & Data Flow

### Two-Stage Pipeline

**Stage 1: Parse** (`pke/parsers/joplin_sync_parser.py`,
`pke/cli/parse_cli.py`)
- Accepts a Joplin sync-folder directory containing raw `.md` files
- Returns `pke/artifacts/parsed/parsed_notes.json`
- Extracts: id, title, body, timestamps, resources, notebook/tag
  metadata via three-pass sync-folder parser
- The Markdown export parser is deprecated and must never be used

**Stage 2: Ingest** (`pke/ingestion/orchestrator.py`,
`pke/cli/ingest.py`)
- Reads parsed JSON; performs deterministic multi-step upsert:
  1. Tag resolution (extract & upsert unique tags)
  2. Notebook resolution (map notebook titles → Supabase IDs)
  3. Note upsert (with computed embeddings via SupabaseClient)
  4. Relationship linking (note ↔ tag, note ↔ notebook)
  5. Chunk upsert (milestone 8.9.6+; not yet implemented)
- Supports `--dry-run` (uses DummyClient, no writes),
  `--limit` (test ingestion)
- Produces `IngestionReport` (processed, inserted, updated,
  skipped, failures counts)

### Embedding Architecture

- Provider: OpenAI text-embedding-3-small (1536 dimensions)
- Client: `pke/embedding/openai_client.py` (implements EmbeddingClient)
- API key: `OPENAI_API_KEY` in `.env` — never committed
- Two embedding levels:
  - Note-level: whole-note embedding in the notes table
  - Chunk-level: per-chunk embedding in the chunks table (8.9.6+)

### Chunking Architecture

Notes above ~1000 characters are split into semantically meaningful
chunks before embedding. Three note archetypes exist in the corpus,
each requiring different chunking logic:

- **Archetype A** (fragmented journal): split on date stamps, merge
  very short entries with neighbors
- **Archetype B** (structured journal): split on date stamps (primary),
  template section headers (secondary for long entries)
- **Archetype C** (reference/medical log): undated opening section
  as its own reference chunk, dated log split on date stamps,
  embedded sub-tables kept intact

Chunking module: `pke/chunking/chunker.py` (milestone 8.9.6)

### Retrieval API

FastAPI endpoint: `POST /query`
- Input: query text, optional filters (notebook, date range, source)
- Output: ranked chunks with note title, notebook, date, matched text,
  similarity score, char offsets, surrounding context
- Hybrid retrieval: chunk-level where chunks exist, whole-note fallback
- Powers both direct search and the Obsidian insight plugin

### Obsidian Insight Plugin

A custom Obsidian plugin (TypeScript) — the primary consumer-facing
expression of the system.

- Watches the active note for changes
- After a short debounce, sends the current paragraph to POST /query
- Renders top 3-5 results in a side panel
- Each result: date, note title, relevant passage (raw text only —
  never AI-generated summaries)
- The panel is ambient, not intrusive; it updates quietly as the
  user writes
- Built with the Obsidian plugin API (TypeScript)
- Lives in: `obsidian-plugin/` at the repo root

**Important:** The Obsidian plugin is TypeScript, not Python. It is
a separate development surface with its own conventions. See the
TypeScript section below before working on plugin files.

### Types & Contracts

All Python types live in **pke/types.py**:
- **NoteRecord**: Supabase row (id, title, body, embedding, metadata,
  resources, notebook_id)
- **IngestionSummary**: Orchestrator output (metrics)
- **EmbeddingClient**: Protocol for pluggable embedding providers

### Supabase Client Abstraction

**SupabaseClient** (`pke/supabase_client.py`):
- Wrapper around real Supabase SDK (or test substitutes)
- Dependency-injected constructor
- Detects DummyClient by classname → forces `dry_run=True`

**DummyClient** (`pke/supabase/dummy_client.py`):
- In-memory stand-in for dry-run and testing
- Prints "Would upsert note: ..." instead of network calls

---

## Developer Workflows

### Python Pipeline — Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configuration:
- Copy `.env.example` → `.env`
- Add `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`

### Python Pipeline — Build & Test Commands

All commands in **Makefile**:
- `make format`: Black auto-format
- `make lint`: flake8 (style + simple bugs)
- `make type`: mypy static type checking
- `make test`: pytest (unit & integration)
- `make check`: Run all above in sequence
- `make fix`: Auto-fix with black + isort

### Python Pipeline — Running Ingestion Locally

```bash
# Stage 1: Parse
pke parse run --export-path /path/to/joplin_export \
  --output pke/artifacts/parsed/parsed_notes.json

# Stage 2: Validate (dry-run)
pke ingest run --parsed-path pke/artifacts/parsed/parsed_notes.json \
  --dry-run

# Stage 3: Real ingestion
pke ingest run --parsed-path pke/artifacts/parsed/parsed_notes.json

# Retrieval API
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Obsidian Plugin — Local Development

```bash
cd obsidian-plugin
npm install
npm run dev       # watch mode, builds to main.js
npm run build     # production build
npm run test      # Jest unit tests
```

The plugin is developed against the Obsidian plugin API. During
development, symlink or copy the plugin folder into an Obsidian
vault's `.obsidian/plugins/pke-insight/` directory to test live.

---

## Key Conventions & Patterns

### Python — Determinism & Testability

- **Orchestrator is pure & linear**: `ingest()` chains deterministic
  steps with no hidden behavior
- **IngestionReport accumulates state** across stages for assertion
  in tests
- **Dependency injection**: SupabaseClient and EmbeddingClient are
  injected; tests supply stubs
- **No global state**: All mutable state passed explicitly

### Python — Parser-Specific Reminders

- The Joplin sync-folder parser is the only active Stage 1 parser;
  `joplin_markdown.py` is deprecated and must not be modified or
  referenced
- Parsers follow the three-pass architecture (load/classify →
  build maps → enrich notes) with no side effects, no network
  calls, and no embedding generation
- Do not skip notes during parsing (except encrypted notes)
- Never use `None` for missing fields; use empty strings or lists
- Notes must be sorted by `id` for deterministic output
- Parsers must not rely on YAML frontmatter assumptions

### Python — Types-First Design

- Type hints are mandatory (mypy enforced in CI)
- TypedDict for cross-module contracts
- Protocol for pluggable clients
- Reason: enables safe refactoring across CLI → ingestion → Supabase

### Python — Module Responsibilities

- **pke/cli/**: Typer entrypoints — argument parsing, env loading,
  output formatting. Delegates work to orchestrator/parsers.
- **pke/parsers/**: File→dict converters. Pure transformation,
  no side effects.
- **pke/embedding/**: EmbeddingClient implementations. One file
  per provider.
- **pke/chunking/**: Note chunking logic. Pure functions, no
  side effects, no network calls.
- **pke/ingestion/**: Multi-step upsert orchestration.
- **pke/supabase_client.py**: Single source for all DB operations.
- **pke/types.py**: Centralized type definitions.

### Python — Testing Patterns

- Unit tests: DummyClient or mock fixtures; assert on counts/structure
- Integration tests: real SupabaseClient + pytest-env for credentials
- E2E tests: full parse → ingest cycle with mocked Supabase
- Fixtures live in `tests/fixtures/`
- No network calls in unit tests

Test-writing guidelines:
- Use `tmp_path` for filesystem isolation
- Import `Path` from `pathlib` for path handling
- Make fixtures deterministic and self-contained

### Python — Code Organization

- Each module has a docstring explaining *why* it exists
- Multi-step functions broken into numbered sections
- Type annotations used throughout
- Avoid inline comments; use docstrings and section headers

### Python — Commentary Standards

When modifying an existing file, always match the commentary style
of the surrounding code. Do not impose a different style.

This project uses the following conventions:

Section headers:
```python
# ----------------------------------------------------------------------
# ⭐ N. Section Title
#
# Explain WHY this section exists, not just what it does.
# Include design decisions, gotchas, and non-obvious reasoning.
# ----------------------------------------------------------------------
```

- Inline comments are brief, on their own line, above the code
- WHY over WHAT — comments explain intent and reasoning, not mechanics
- Do not use docstrings where section headers are the established pattern
- Do not add generic or redundant comments that restate the code
- When adding a new numbered section, continue the existing sequence

---

## TypeScript — Obsidian Plugin Conventions

The Obsidian plugin is a separate development surface from the Python
pipeline. It is TypeScript, uses the Obsidian plugin API, and has
different conventions.

### Plugin Structure

```
obsidian-plugin/
  src/
    main.ts          ← plugin entry point, registers commands and views
    insight-panel.ts ← side panel UI component
    retrieval.ts     ← PKE API client (calls POST /query)
    debounce.ts      ← debounce utility for editor change events
    types.ts         ← TypeScript interfaces for API responses
  tests/
    retrieval.test.ts
    debounce.test.ts
  manifest.json      ← Obsidian plugin manifest
  package.json
  tsconfig.json
```

### TypeScript Conventions

- Strict TypeScript (`"strict": true` in tsconfig)
- Interfaces over type aliases for API contracts
- Async/await over raw promises
- No `any` types — define interfaces for all API responses
- Error boundaries around all API calls — plugin must never crash
  Obsidian even if the PKE API is unavailable

### Plugin Behavior Contracts

- The plugin must degrade gracefully when the PKE API is offline.
  If the retrieval API is unreachable, the insight panel shows a
  subtle "PKE offline" indicator and no error is thrown.
- Debounce: editor changes trigger a retrieval call after 2000ms
  of inactivity. Do not fire on every keystroke.
- The panel renders raw passage text, date, and note title only.
  It never generates or displays AI-produced summaries.
- The panel must never interrupt the writing flow. No modal dialogs,
  no focus stealing, no aggressive animations.
- All API calls include a timeout (default 5000ms). Slow responses
  are silently dropped, not surfaced as errors.

### TypeScript Testing

- Jest for unit tests
- Mock the Obsidian API in tests — do not depend on a live vault
- Mock the PKE retrieval API — do not make real HTTP calls in tests
- Test the debounce logic, API client, and response rendering
  independently

### Plugin — Commentary Standards

- JSDoc for all exported functions and interfaces
- WHY over WHAT — same philosophy as the Python codebase
- Section comments for logical blocks within a file:

```typescript
// ─────────────────────────────────────────────
// N. Section Title
//
// Explain why this section exists.
// ─────────────────────────────────────────────
```

---

## Adding Features

### Adding a New Parser (Python)

1. Create `pke/parsers/my_format.py` with a pure
   `parse_notes(source_path) -> List[dict]` entrypoint
2. Follow the three-pass architecture of joplin_sync_parser.py
3. Add or extend types in `pke/types.py` if needed
4. Add a CLI command in `pke/cli/parse_cli.py`
5. Add tests with fixtures in `tests/fixtures/`
6. Update README.md if user-facing

### Adding an Embedding Provider (Python)

1. Implement `EmbeddingClient` protocol in `pke/embedding/`
2. SupabaseClient constructor accepts `embedding_client=` parameter
3. Update `.env.example` with new API key
4. Add tests with mocked embeddings

### Adding a New Ingestion Resolution Step (Python)

1. Create `pke/ingestion/my_resolution.py` with pure functions
2. Update `orchestrator.py` to call it in the correct sequence
3. Update `IngestionReport` to track relevant metrics
4. Add tests asserting on IngestionReport state

### Adding a Plugin Feature (TypeScript)

1. Define the interface contract in `src/types.ts` first
2. Implement in the appropriate src/ module
3. Add Jest tests before or alongside implementation
4. Verify graceful degradation when PKE API is offline
5. Verify the feature does not interrupt the writing flow

---

## Common Pitfalls

### Python

- **Don't call SupabaseClient.from_env() inside orchestrator**:
  inject via constructor
- **Don't mutate parsed notes dict**: create new dicts for
  transformed data
- **Don't skip type hints**: mypy is enforced
- **Don't add logic to the CLI layer**: parse args, load env,
  call orchestrator, format output — nothing else
- **Don't commit .env**: use .env.example as template
- **Don't skip --dry-run testing**: always validate before real writes
- **Don't modify joplin_markdown.py**: it is deprecated
- **Don't modify the orchestrator or Supabase schema** without a
  formal design decision from CURRENT_TASK.md
- **Don't generate embeddings inside a parser**
- **Don't sort notes by title**: always sort by `id`

### TypeScript / Obsidian Plugin

- **Don't crash Obsidian**: all plugin errors must be caught and
  handled gracefully
- **Don't call the PKE API synchronously**: always async/await
- **Don't render AI-generated text in the panel**: raw passages only
- **Don't fire retrieval on every keystroke**: debounce is mandatory
- **Don't use `any`**: define interfaces for all external data
- **Don't steal focus**: the panel is read-only and ambient

---

## References

### Python Pipeline
- **README.md**: High-level overview, quickstart, env setup
- **ARCHITECTURE.md**: Full system architecture, authoritative reference
- **ROADMAP.md**: Strategic direction, milestone sequence, vision
- **CURRENT_TASK.md**: Active milestone spec — always read this first
- **CONTRIBUTING.md**: Git workflow, pre-commit checks
- **pyproject.toml**: Tool config (black, isort, flake8, mypy)
- **pytest.ini**: Test env loading, plugin config
- **tests/conftest.py**: Shared fixtures, mock factories
- **pke/types.py**: Type contracts
- **pke/ingestion/orchestrator.py**: Canonical ingestion logic

### Obsidian Plugin
- **obsidian-plugin/src/main.ts**: Plugin entry point
- **obsidian-plugin/src/types.ts**: TypeScript contracts
- **Obsidian Plugin API docs**: https://docs.obsidian.md/Plugins/Getting+started/Build+a+plugin
