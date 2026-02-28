"""
Root entrypoint for the Personal Knowledge Engine CLI.

Milestone 8 migrates the CLI from Click to Typer to support:

    • nested command groups (e.g., `pke notes upsert`)
    • rich help output
    • type‑hint‑driven argument parsing
    • a more maintainable, contributor‑friendly structure

This module defines the top‑level `pke` command and mounts sub‑apps
from other modules under pke/cli/, such as:

    • pke/cli/notes_cli.py   →  `pke notes ...`
    • pke/cli/ingest.py      →  `pke ingest ...`
    • pke/cli/parse_cli.py   →  `pke parse ...`

Together, these form a complete ingestion pipeline:

    Stage 1: `pke parse run`
        Parse a Joplin export directory into a structured JSON artifact.
        Default output:
            pke/artifacts/parsed/parsed_notes.json

    Stage 2: `pke ingest run`
        Ingest the parsed JSON into Supabase.
        Default input:
            pke/artifacts/parsed/parsed_notes.json
"""

# ---------------------------------------------------------------------------
# Imports (must be at top to satisfy flake8 E402)
# ---------------------------------------------------------------------------
from dotenv import load_dotenv
import typer

from .notes_cli import notes_app
from .ingest import ingest_app
from .parse_cli import parse_app

# Load environment variables
load_dotenv()

# ---------------------------------------------------------------------------
# Root CLI application
# ---------------------------------------------------------------------------
cli = typer.Typer(
    help=(
        "Personal Knowledge Engine command‑line interface.\n\n"
        "This CLI exposes a two‑stage ingestion pipeline:\n\n"
        "  Stage 1 — Parse Joplin exports:\n"
        "      pke parse run --export-path <folder>\n\n"
        "  Stage 2 — Ingest parsed notes into Supabase:\n"
        "      pke ingest run --parsed-path pke/artifacts/parsed/parsed_notes.json\n\n"
        "Additional commands (e.g., `pke notes`) support note management "
        "and future extensions to the system."
    )
)

# ---------------------------------------------------------------------------
# Register sub‑applications
# ---------------------------------------------------------------------------
cli.add_typer(notes_app, name="notes")
cli.add_typer(ingest_app, name="ingest")
cli.add_typer(parse_app, name="parse")

# ---------------------------------------------------------------------------
# Entry point for `python -m pke.cli.main`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cli()
