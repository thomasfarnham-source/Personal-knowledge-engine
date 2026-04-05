# Content Curation Agent

A multi-agent content curation system that scans sources, applies editorial
judgment, finds connections to personal history and reading, and delivers
daily drops and weekly synthesis briefs to an Obsidian vault.

## Architecture

Four agents in a sequential pipeline:

```
Scout → Editor → Connector → Composer
```

**Scout** — Scans RSS feeds and NewsAPI for raw material. Follows the
mandate document (MANDATE.md). Applies no editorial judgment beyond
basic relevance filtering. Its job is coverage, not taste.

**Editor** — Filters the Scout's output using Claude API. Applies the
three-pillar mandate with kill criteria. Monitors Scout performance
(kill rates by source, pillar coverage gaps). Targets 5-8 items daily.

**Connector** — Queries the PKE Retrieval API and book database for
adjacencies between curated content and personal history. Does not force
connections — silence is better than a stretch.

**Composer** — Assembles two outputs:
  - Daily drop: 3-5 items, scannable in 5 minutes, delivered to Obsidian
  - Weekly synthesis: patterns, strongest connections, pillar health,
    post seeds, delivered to Obsidian on Sunday

## Governance Model

The Scout has autonomy within a written mandate (MANDATE.md).
The Editor functions as both filter and monitor.
The Producer (Tom) reviews the raw feed monthly to recalibrate.

"Ambition counteracting ambition." — Madison, Federalist 51

## Usage

### Daily pipeline
```bash
python -m scripts.content_agent.pipeline --daily --vault-path /path/to/vault
```

### Weekly synthesis
```bash
python -m scripts.content_agent.pipeline --weekly --vault-path /path/to/vault
```

### Individual agents
```bash
python -m scripts.content_agent.scout --dry-run
python -m scripts.content_agent.editor --dry-run
python -m scripts.content_agent.connector --skip-pke --dry-run
python -m scripts.content_agent.composer --daily
```

## Dependencies

```
pip install feedparser requests
```

## Environment Variables

```
NEWSAPI_KEY=your_newsapi_key          # Free tier: newsapi.org
ANTHROPIC_API_KEY=your_anthropic_key  # For Editor and Connector
```

## File Structure

```
scripts/content_agent/
    MANDATE.md       — Scout constitution (three pillars + kill criteria)
    README.md        — This file
    sources.json     — RSS feeds and NewsAPI query configuration
    books.json       — Book club reading list with thematic tags
    scout.py         — Raw material scanner
    editor.py        — Editorial filter (Claude-powered)
    connector.py     — Personal corpus and book adjacency finder
    composer.py      — Daily drop and weekly synthesis assembler
    pipeline.py      — Full pipeline orchestrator
    output/
        raw/         — Scout raw feeds (JSON + markdown)
        filtered/    — Editor filtered output (JSON + markdown)
        connected/   — Connector annotated output (JSON)
        briefs/      — Composer daily drops and weekly syntheses
```

## Book Database

The `books.json` file is populated by Tom over time. Each book entry has:
- Title, author, year read
- Themes (3-5 broad concepts)
- Keywords (more specific terms for matching)
- Core idea (one-sentence synthesis)
- Personal note (reaction or connection)

The Connector queries by theme, not by title — "which books connect to
the concept of governance?" returns relevant entries across the full list.

## PKE Integration

The Connector queries the PKE Retrieval API (localhost:8000) to find
personal journal entries, messages, and email that connect to curated
content. This is what makes the system distinctively personal — no
generic curation tool can pair a Financial Times article with a journal
entry from 2019 where you were wrestling with the same question.

Start the PKE API before running the pipeline:
```bash
uvicorn pke.api.main:app --reload
```
