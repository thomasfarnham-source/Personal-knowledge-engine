"""
Ingestion command‑line interface for the Personal Knowledge Engine.

This module defines the `ingest` command group for the Typer‑based CLI.

Milestone 8 goal:
    • Migrate from Click to Typer for consistency with the new `notes` CLI.
    • Keep ingestion logic thin and delegated to the orchestrator.
    • Provide a clear, contributor‑friendly interface for running ingestion.

Public surface:

    • `ingest_app`  → mounted in pke/cli/main.py as:

          pke ingest run --parsed-path parsed_notes.json --dry-run --limit 10
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import typer

from pke.ingestion.orchestrator import ingest_notes
from pke.supabase_client import SupabaseClient

# ---------------------------------------------------------------------------
# Sub‑application definition
# ---------------------------------------------------------------------------
# This Typer app is mounted under the name "ingest" in pke/cli/main.py:
#
#       app.add_typer(ingest_app, name="ingest")
#
# which yields commands like:
#
#       pke ingest run ...
# ---------------------------------------------------------------------------
ingest_app = typer.Typer(
    help="Commands for ingesting parsed notes into Supabase.",
)


# ---------------------------------------------------------------------------
# Command: pke ingest run
# ---------------------------------------------------------------------------
# This replaces the old Click @click.command() entrypoint. The behavior
# is intentionally thin: parse flags, then delegate to `run_ingest()`.
# ---------------------------------------------------------------------------
@ingest_app.command("run")
def ingest_command(
    parsed_path: str = typer.Option(
        "parsed_notes.json",
        "--parsed-path",
        help="Path to the parsed notes JSON file.",
        show_default=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run ingestion without writing to Supabase.",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Limit the number of notes ingested.",
    ),
) -> None:
    """
    Ingest parsed notes into Supabase using the orchestrator.

    This is the Typer-facing command. It parses CLI flags and delegates
    the actual ingestion work to `run_ingest()`.
    """
    run_ingest(parsed_path=parsed_path, dry_run=dry_run, limit=limit)


def run_ingest(
    parsed_path: str = "parsed_notes.json",
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    CLI entrypoint for ingestion. Thin wrapper around the orchestrator.

    Responsibilities:

        1. Locate and load the parsed notes file.
        2. Apply an optional limit for faster, controlled runs.
        3. Instantiate a SupabaseClient (real or dry-run).
        4. Delegate ingestion to the orchestrator.
        5. Print a human-readable summary for CLI users.

    This function deliberately does NOT:

        • implement ingestion logic itself
        • talk directly to Supabase tables
        • know about notebooks, tags, or relationships
    """
    path = Path(parsed_path)

    if not path.exists():
        raise FileNotFoundError(f"{parsed_path} not found. Run parse_joplin_sync first.")

    notes = json.loads(path.read_text(encoding="utf-8"))

    if limit is not None:
        notes = notes[:limit]

    client = SupabaseClient(dry_run=dry_run)

    summary = ingest_notes(notes, client)

    print("\n=== Ingestion Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    return summary
