# Personal Knowledge Engine

A personal intelligence layer that surfaces diary reflections and
past thinking while you write — connecting who you are now to who
you were then.

The system ingests personal notes, messages, and email into a
semantic knowledge base, then exposes that knowledge through a
live insight panel inside Obsidian. As you write a journal entry,
relevant passages from your own history appear quietly beside you —
not because you searched for them, but because the system recognized
the connection.

---

## What It Does

**Ingestion pipeline** — a deterministic, two-stage pipeline that
parses personal notes into a structured, queryable knowledge base
backed by Supabase and OpenAI embeddings.

**Semantic chunking** — long notes (journal entries, medical logs,
reference notes) are split into semantically meaningful chunks so
that a specific paragraph from three years ago is retrievable, not
buried inside a whole-note embedding.

**Retrieval API** — a FastAPI backend that accepts natural language
queries and returns the most relevant passages from your personal
history, with enough context to understand what you were thinking.

**Obsidian insight plugin** — a TypeScript plugin for Obsidian that
watches your active note and surfaces relevant historical passages
in a side panel as you write. The writing process stays yours.
The system provides material for reflection, not conclusions.

---

## Current State

| Milestone | Description | Status |
|-----------|-------------|--------|
| 8.9.4 | Deterministic ingestion baseline | ✅ Complete |
| 8.9.5 | Real OpenAI embeddings + chunk schema | 🔄 In progress |
| 8.9.6 | Chunking for long notes | 🔵 Planned |
| 8.9.7 | Retrieval API | 🔵 Planned |
| 8.9.8 | Obsidian insight plugin | 🔵 Planned |
| 8.9.9 | Insight generation | 🔵 Planned |

See `ROADMAP.md` for the full milestone sequence and design notes.

---

## 🚀 Quickstart

### 1. Clone and set up the environment

```bash
git clone https://github.com/<your-org>/personal-knowledge-engine.git
cd personal-knowledge-engine

python -m venv .venv

# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
OPENAI_API_KEY=your-openai-api-key
```

These values stay local only. `.env` is intentionally ignored by Git.

---

## 🧩 Ingestion Pipeline

The pipeline runs in two explicit stages.

### Stage 1 — Parse

Converts a Joplin sync folder into a structured JSON artifact.

```bash
pke parse run \
  --export-path path/to/joplin_sync_folder \
  --output pke/artifacts/parsed/parsed_notes.json
```

Output: `pke/artifacts/parsed/parsed_notes.json` — the only input
to Stage 2.

### Stage 2 — Ingest

Upserts parsed notes into Supabase with real semantic embeddings.

```bash
# Validate without writing (always run this first)
pke ingest run \
  --parsed-path pke/artifacts/parsed/parsed_notes.json \
  --dry-run

# Real ingestion
pke ingest run \
  --parsed-path pke/artifacts/parsed/parsed_notes.json

# Limit for testing
pke ingest run --limit 10
```

The pipeline is deterministic and idempotent. Running it twice
produces identical Supabase state.

---

## 🧠 Retrieval API

Start the FastAPI backend:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Explore the API at `http://localhost:8000/docs`.

Key endpoint (milestone 8.9.7):

```
POST /query
{
  "text": "what did I think about Killian's medication",
  "filters": { "notebook": "Journal", "date_from": "2023-01-01" }
}
```

Returns ranked passages from your personal history with note title,
date, matched text, similarity score, and character offsets for
context expansion.

---

## ✍️ Obsidian Insight Plugin

The plugin lives in `obsidian-plugin/`. It connects Obsidian to
the PKE retrieval API and surfaces relevant historical passages
in a side panel as you write.

### Plugin setup

```bash
cd obsidian-plugin
npm install
npm run dev    # watch mode
npm run build  # production build
npm run test   # Jest unit tests
```

To test in a live vault, symlink or copy the plugin folder into
your vault's `.obsidian/plugins/pke-insight/` directory.

### Plugin behavior

- Watches your active note for changes
- After a 2-second pause in typing, queries `POST /query` with
  your current paragraph
- Renders the top 3-5 matching passages in a side panel
- Shows: date, note title, and the relevant passage (raw text only)
- Degrades gracefully when the PKE API is offline
- Never interrupts the writing flow

---

## 🗂 Project Structure

```
pke/
  cli/               # Typer CLI entrypoints (parse, ingest, notes)
  parsers/           # Note source parsers (Joplin sync-folder)
  embedding/         # EmbeddingClient implementations (OpenAI)
  chunking/          # Note chunking logic (milestone 8.9.6)
  ingestion/         # Orchestrator + Supabase integration
  supabase_client.py # Single source for all DB operations
  types.py           # Centralized type contracts
  artifacts/         # Generated pipeline artifacts (gitignored)

obsidian-plugin/
  src/
    main.ts          # Plugin entry point
    insight-panel.ts # Side panel UI
    retrieval.ts     # PKE API client
    types.ts         # TypeScript interfaces
  tests/             # Jest unit tests

scripts/
  add_chunks_table.sql      # Supabase migration: chunks table
  reset_ingestion_tables.sql # Full reset script
  inspect_schema.sql         # Diagnostic queries

tests/
  fixtures/          # Parsed note examples, sync-folder samples
  conftest.py        # Shared fixtures and mock factories

main.py              # FastAPI entrypoint
```

---

## 🔐 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key |
| `OPENAI_API_KEY` | Yes | OpenAI API key for embeddings |

Keep real secrets out of the repo. Only `.env.example` is tracked.

---

## 🧪 Build & Test

All commands via `make`:

```bash
make format   # Black auto-format
make lint     # flake8
make type     # mypy static type checking
make test     # pytest (unit + integration)
make check    # all of the above
make fix      # auto-fix with black + isort
```

---

## 📚 Key Documents

| Document | Purpose |
|----------|---------|
| `ARCHITECTURE.md` | Full system architecture — authoritative reference |
| `ROADMAP.md` | Strategic vision, milestone sequence, design notes |
| `CURRENT_TASK.md` | Active milestone spec — read this before starting work |
| `.github/copilot-instructions.md` | AI coding guidelines for Copilot |

---

## 🚀 Deployment

- **Pipeline**: runs locally on demand or via scheduled job
- **Retrieval API**: Render, Fly.io, Railway, or any container platform
- **Secrets**: GitHub Secrets or platform config vars
- **Obsidian plugin**: installed locally in your Obsidian vault

---

## 📄 License

Add your preferred license (MIT, Apache 2.0, or private) and
update this section.