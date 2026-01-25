from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import click

from pke.ingestion.orchestrator import ingest_notes
from pke.supabase_client import SupabaseClient


@click.command()
@click.option(
    "--parsed-path",
    default="parsed_notes.json",
    help="Path to the parsed notes JSON file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Run ingestion without writing to Supabase.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Limit the number of notes ingested.",
)
def ingest(parsed_path: str, dry_run: bool, limit: Optional[int]) -> None:
    """
    Ingest parsed notes into Supabase using the orchestrator.

    This is the Click-facing command. It parses CLI flags and delegates
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

    This function is intentionally narrow in scope:

        • It does NOT implement ingestion logic itself.
        • It does NOT talk directly to Supabase tables.
        • It does NOT know about notebooks, tags, or relationships.

    Instead, it is responsible for:

        1. Locating and loading the parsed notes file.
        2. Applying an optional limit for faster, controlled runs.
        3. Instantiating a SupabaseClient (real or dry-run).
        4. Delegating the actual ingestion to the orchestrator.
        5. Printing a human-readable summary for CLI users.
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
