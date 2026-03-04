# Personal Knowledge Engine — AI Coding Guidelines

## AI-Assisted Development Workflow

This project uses a structured three-step collaboration model between **Thomas** (owner), **Claude** (system-level reasoning), and **VS Code Copilot** (file-level implementation).

### Roles

- **Thomas**: Owner and final authority. Defines problems, approves all architectural decisions and code.
- **Claude (External)**: System-level reasoning. Defines module boundaries, contracts, schemas, failure modes, and architectural coherence. Does *not* write code.
- **VS Code Copilot**: File-level implementation. Writes functions, generates tests, refactors modules, updates imports. Does *not* make architectural decisions.

### Three-Step Development Loop

1. **System-Level Design** (Thomas + Claude)
   - Output: `CURRENT_TASK.md` specification
   - Includes: function signatures, contracts, acceptance criteria, constraints, test cases, open questions
   - This is the handoff to VS Code Copilot

2. **File-Level Implementation** (VS Code Copilot)
   - Uses the specification to write code, tests, and refactors
   - Thomas reviews before proceeding

3. **System-Level Review** (Thomas + Claude)
   - Checklist: signatures match? determinism preserved? failure modes explicit? tests present? no hidden coupling? aligned with constraints?
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

Update this file at the end of every session; paste it at the start of the next to carry context forward.

### Guiding Principles

- Thomas owns every decision. AI proposes; Thomas approves.
- Architecture is explicit, not implicit.
- Contracts are written before code is written.
- Tests define correctness.
- Review enforces determinism and clarity.

---

## Project Overview

**Personal Knowledge Engine** is a two-stage ingestion pipeline that parses, stores, and queries personal notes. It combines:
- A **Typer CLI** (pke parse, pke ingest, pke notes) for ergonomic command-line workflows
- A **FastAPI backend** (main.py) for REST queries over parsed notes
- **Supabase storage** with embeddings, tags, notebooks, and resources as first-class entities
- **Pluggable parsers** (currently Joplin sync-folder parser) for extensible source imports

The canonical workflow is: `pke parse run` (now using the sync-folder parser) → `pke ingest run --dry-run` → `pke ingest run` → API queries.

## Architecture & Data Flow

### Two-Stage Pipeline

**Stage 1: Parse** (`pke/parsers/joplin_sync_parser.py`, `pke/cli/parse_cli.py`)
- Accepts a Joplin sync-folder directory containing raw `.md` files
- Returns `pke/artifacts/parsed/parsed_notes.json` (structured, lossless representation)
- Extracts: id, title, body, timestamps, resources, notebook/tag metadata via three-pass sync-folder parser

  The earlier Markdown export parser is deprecated, kept only for reference, and must never be used; the sync-folder parser is now the canonical Stage 1 implementation.

**Stage 2: Ingest** (`pke/ingestion/orchestrator.py`, `pke/cli/ingest.py`)
- Reads parsed JSON; performs deterministic multi-step upsert:
  1. **Tag resolution** (extract & upsert unique tags)
  2. **Notebook resolution** (map notebook titles → Supabase IDs)
  3. **Note upsert** (with computed embeddings via SupabaseClient)
  4. **Relationship linking** (note ↔ tag, note ↔ notebook)
- Supports `--dry-run` (uses DummyClient, no writes), `--limit` (test ingestion)
- Produces `IngestionReport` (processed, inserted, updated, skipped, failures counts)

### Types & Contracts

All types live in **pke/types.py**:
- **NoteRecord**: Supabase row (id, title, body, embedding, metadata, resources, notebook_id)
- **IngestionSummary**: Orchestrator output (SupabaseClient calls and metrics)
- **EmbeddingClient**: Protocol for pluggable embedding providers

Reason: Single source of truth for CLI ↔ ingestion ↔ Supabase contracts; enables deterministic testing.

### Supabase Client Abstraction

**SupabaseClient** (`pke/supabase_client.py`):
- Wrapper around real Supabase SDK (or test substitutes)
- Dependency-injected constructor: accepts real client, DummyClient, or test stubs
- Detects DummyClient by classname (`__name__ == "DummyClient"`) → forces `dry_run=True`
- Public methods: `resolve_notebook_id()`, `upsert_note_with_embedding()`, `upsert_tags()`, `upsert_note_tag_relationships()`

**DummyClient** (`pke/supabase/dummy_client.py`):
- Minimal in-memory stand-in; prints "Would upsert note: ..." instead of network calls
- Used by orchestrator to validate pipeline shape without side effects
- Tests can assert on call counts by passing mock clients

## Developer Workflows

### Local Development

**Environment Setup:**
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
```

**Configuration:**
- Copy `.env.example` → `.env`
- Add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (kept local; .env is .gitignore'd)

### Build & Test Commands

All commands in **Makefile**:
- `make format`: Black auto-format
- `make lint`: flake8 (style + simple bugs)
- `make type`: mypy static type checking
- `make test`: pytest (unit & integration)
- `make check`: Run all above in sequence
- `make fix`: Auto-fix with black + isort

**Test Setup:**
- **pytest.ini**: Loads `.env` for secrets (SUPABASE_URL, etc.)
- **tests/conftest.py**: Centralizes fixtures (cli_runner, load_json_fixture, mock Supabase clients)
- **tests/fixtures/**: Parsed note examples, expected outputs, Joplin sync-folder samples

### Running Ingestion Locally

```bash
# Stage 1: Parse a Joplin export (requires actual export directory)
pke parse run --export-path /path/to/joplin_export --output pke/artifacts/parsed/parsed_notes.json

# Stage 2: Validate (dry-run; no DB writes)
pke ingest run --parsed-path pke/artifacts/parsed/parsed_notes.json --dry-run

# Stage 3: Real ingestion (requires valid Supabase credentials in .env)
pke ingest run --parsed-path pke/artifacts/parsed/parsed_notes.json

# Query API (if running via FastAPI)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# Then visit http://localhost:8000/docs for Swagger UI
```

## Key Conventions & Patterns

### Determinism & Testability

- **Orchestrator is pure & linear**: `ingest()` method chains deterministic steps with no hidden behavior
- **IngestionReport accumulates state** across stages for easy assertion in tests
- **Dependency injection**: SupabaseClient and EmbeddingClient are injected; tests can supply stubs
- **No global state**: All mutable state is passed explicitly through function calls

#### Parser-specific reminders

- The Joplin sync-folder parser is the only active Stage 1 parser; the Markdown exporter (`joplin_markdown.py`) is deprecated and must not be modified or referenced.
- Parsers must follow the three-pass architecture (load/classify → build maps → enrich notes) with no side effects, no network calls, and no embedding generation.
- Do not skip any notes during parsing (except encrypted notes, which should be logged and ignored).
- Never use `None` for missing notebook, tag, or timestamp fields; use empty strings or empty lists instead.
- Notes must be sorted by `id` for deterministic output.
- Parsers should not rely on YAML frontmatter or any Markdown-specific assumptions.

### Types-First Design

- Type hints are mandatory (mypy enforced in CI)
- TypedDict for cross-module contracts (NoteRecord, IngestionSummary)
- Protocol for pluggable clients (EmbeddingClient, SupabaseClient)
- Reason: Enables safe refactoring across CLI → ingestion → Supabase layers

### Module Responsibilities

- **pke/cli/**: Typer entrypoints (parse_cli.py, ingest.py, notes_cli.py, main.py)
  - Argument parsing, environment loading, CLI output formatting
  - Delegates actual work to orchestrator/parsers
- **pke/parsers/**: File→dict converters (joplin_sync_parser.py)
  - No I/O side effects; pure transformation functions (three‑pass parser architecture)
- **pke/ingestion/**: Multi-step upsert orchestration (orchestrator.py + resolution modules)
  - Tag extraction (tag_resolution.py), notebook lookup (notebook_resolution.py), resource linking
  - Works with injected SupabaseClient
- **pke/supabase_client.py**: SupabaseClient wrapper (single source for all DB operations)
- **pke/types.py**: Centralized type definitions (shared across all modules)

### Testing Patterns

- **Unit tests**: Use DummyClient or mock fixtures in conftest.py; assert on counts/structure
- **Integration tests**: Use real SupabaseClient + pytest-env to load actual Supabase credentials
- **E2E tests**: full parse → ingest cycle with mocked Supabase, verify IngestionReport
- **Fixtures live in tests/fixtures/** (parsed_notes.json examples, Joplin sync-folder samples)
- **No network calls in unit tests**: Stub clients make CI fast and reliable

#### Test-writing guidelines

- Write parser tests in the file specified by the current task (e.g., `tests/test_joplin_sync_parser.py`).
- Use `tmp_path` fixtures for filesystem isolation and import `Path` from `pathlib` when dealing with paths.
- Avoid any real network calls; use mocks or DummyClient for Supabase interactions.
- Make fixtures deterministic and self‑contained to ensure repeatable results.

### Code Organization

- Each module has a docstring explaining *why* it exists (not just what it does)
- Multi-step functions are broken into numbered sections (e.g., "# 1 — PARSE A SINGLE NOTE")
- Type annotations are used for contract clarity (mypy enforces correctness)
- Avoid inline comments; use docstrings and section headers instead

## Adding Features

### Adding a New Parser

1. Prefer the sync-folder parser (`pke/parsers/joplin_sync_parser.py`) as the canonical Stage 1 implementation; new parsers should follow the same three-pass style.
2. For a different source format, create `pke/parsers/my_format.py` with a pure `parse_notes(source_path) -> List[dict]` entrypoint.
3. Add or extend types in `pke/types.py` if format-specific metadata is required.
4. Add a CLI command or flag in `pke/cli/parse_cli.py` if the new parser should be exposed (e.g., `pke parse my_format --source-path ...`).
5. Add tests in `tests/test_parse_note.py` or a dedicated test file; use fixtures under `tests/fixtures/` that reflect the new source format.
6. Update README.md with usage example if the parser is user-facing.

### Adding an Embedding Provider

1. Implement `EmbeddingClient` protocol in `pke/embedding/` (e.g., openai_client.py)
2. SupabaseClient constructor already accepts `embedding_client=` parameter
3. Update environment variables in `.env.example` (e.g., OPENAI_API_KEY)
4. Add tests in `tests/test_supabase_client.py` with mocked embeddings

### Adding a New Ingestion Resolution Step

1. Create `pke/ingestion/my_resolution.py` with pure functions (no side effects)
2. Update `orchestrator.py` to call your function in the correct sequence
3. Update `IngestionReport` to track relevant metrics (if needed)
4. Add tests that assert on IngestionReport state after each step

## Common Pitfalls

- **Don't call SupabaseClient.from_env() inside orchestrator**: Inject the client via constructor parameter for testability
- **Don't mutate parsed notes dict**: Create new dicts for transformed data; immutability aids debugging
- **Don't skip type hints**: mypy is enforced; use TypedDict for complex returns
- **Don't add logic to the CLI layer**: CLI should parse args, load env, call orchestrator, format output
- **Don't commit .env**: It contains secrets; use .env.example as template
- **Don't skip --dry-run testing**: Always validate ingestion with DummyClient before real writes

### Parser Constraints

- **Do not modify `joplin_markdown.py`** or rely on the Markdown export format; it is deprecated.
- **Do not modify the orchestrator or Supabase schema**; these are fixed contracts.
- **Do not generate embeddings inside a parser**; embedding computation belongs to the ingestion layer.
- **Do not skip notes** during parsing (encrypted notes may be skipped with a warning).
- **Do not use `None` for missing fields**; use empty string or empty list as specified by the ParsedNote contract.
- **Do not add new dependencies** for parsing logic; keep the dependency graph minimal.
- **Do not sort notes by title** – always sort by `id` for determinism.
- **Do not mix sync-folder and markdown logic**; keep parser implementations separate.

## References

- **README.md**: High-level overview, quickstart, env setup
- **CONTRIBUTING.md**: Git workflow, pre-commit checks, issue/PR process
- **pyproject.toml**: Centralized tool config (black, isort, flake8, mypy)
- **pytest.ini**: Test env loading, plugin config
- **tests/conftest.py**: Shared fixtures, mock factories
- **pke/types.py**: Type contracts (NoteRecord, IngestionSummary, EmbeddingClient)
- **pke/ingestion/orchestrator.py**: Canonical ingestion logic; start here for data flow
