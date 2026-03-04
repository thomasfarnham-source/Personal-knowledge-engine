"""
Ingestion command‑line interface for the Personal Knowledge Engine.

This module defines the `ingest` command group for the Typer‑based CLI.

Milestone 8 goal:
    • Migrate from Click to Typer for consistency with the new `notes` CLI.
    • Keep ingestion logic thin and delegated to the orchestrator.
    • Provide a clear, contributor‑friendly interface for running ingestion.

Public surface:

    • `ingest_app`  → mounted in pke/cli/main.py as:

          pke ingest run --parsed-path pke/artifacts/parsed/parsed_notes.json --dry-run --limit 10
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import typer
import os

# ⭐ NEW: The CLI must instantiate the real Supabase SDK client.
from supabase import create_client

# ⭐ Our wrapper client, which expects an SDK client inside it.
from pke.supabase_client import SupabaseClient

# ⭐ The orchestrator accepts (notes, client, dry_run)
from pke.ingestion.orchestrator import ingest_notes

# ---------------------------------------------------------------------------
# Sub‑application definition
# ---------------------------------------------------------------------------
ingest_app = typer.Typer(
    help=(
        "Stage 2 of the ingestion pipeline.\n\n"
        "Consumes the parsed notes artifact produced by:\n\n"
        "    pke parse run\n\n"
        "By default, ingestion reads from:\n\n"
        "    pke/artifacts/parsed/parsed_notes.json\n\n"
        "Use --parsed-path to override the input file, and --dry-run to "
        "simulate ingestion without writing to Supabase."
    )
)


# ---------------------------------------------------------------------------
# Command: pke ingest run
# ---------------------------------------------------------------------------
@ingest_app.command("run")
def ingest_command(
    parsed_path: Path = typer.Option(
        Path("pke/artifacts/parsed/parsed_notes.json"),
        "--parsed-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the parsed notes JSON file produced by `pke parse run`.",
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

    This command loads the parsed notes artifact, applies an optional limit,
    and delegates ingestion to the orchestrator. Use --dry-run to validate
    ingestion behavior without performing any writes.
    """
    run_ingest(parsed_path=parsed_path, dry_run=dry_run, limit=limit)


def run_ingest(
    parsed_path: Path = Path("pke/artifacts/parsed/parsed_notes.json"),
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    CLI entrypoint for ingestion. Thin wrapper around the orchestrator.

    Responsibilities:

        1. Locate and load the parsed notes file.
        2. Apply an optional limit for faster, controlled runs.
        3. Instantiate the Supabase client (SDK + wrapper).
        4. Delegate ingestion to the orchestrator.
        5. Print a human-readable summary for CLI users.

    This function deliberately does NOT:

        • implement ingestion logic itself
        • talk directly to Supabase tables
        • know about notebooks, tags, or relationships
    """

    # ----------------------------------------------------------------------
    # 1. Validate the parsed notes file exists
    # ----------------------------------------------------------------------
    if not parsed_path.exists():
        raise FileNotFoundError(f"{parsed_path} not found. Run `pke parse run` first.")

    # ----------------------------------------------------------------------
    # 2. Load parsed notes
    # ----------------------------------------------------------------------
    notes = json.loads(parsed_path.read_text(encoding="utf-8"))

    if limit is not None:
        notes = notes[:limit]

    # ----------------------------------------------------------------------
    # ⭐ 3. Instantiate the correct Supabase client
    #
    # The CLI is responsible for dependency creation.
    # The orchestrator receives the client and uses it.
    #
    # Dry-run and real mode require different clients:
    #
    #   --dry-run → DummyClient (no network calls, no credentials needed)
    #   real mode → real Supabase SDK client (requires credentials)
    #
    # WHY THIS MATTERS:
    #   The real SDK client must never be constructed in dry-run mode.
    #   Doing so causes the orchestrator to call real Supabase methods
    #   with unresolved notebook names instead of UUIDs, producing a
    #   uuid syntax error.
    #
    # We load SUPABASE_URL and SUPABASE_KEY from the environment.
    # These are populated via python-dotenv in pke/cli/main.py.
    # ----------------------------------------------------------------------
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if dry_run:
        # Dry-run: use DummyClient — no credentials required
        from pke.supabase.dummy_client import DummyClient

        client = SupabaseClient(DummyClient())
    else:
        # Real mode: credentials are required
        if not url or not key:
            raise RuntimeError(
                "Supabase credentials not found. Ensure SUPABASE_URL and SUPABASE_KEY "
                "are set in your environment or .env file."
            )
        # Create the official Supabase SDK client
        sdk_client = create_client(url, key)
        # Wrap it in our project-specific client
        client = SupabaseClient(sdk_client)

    # ----------------------------------------------------------------------
    # ⭐ 4. Delegate to orchestrator with correct signature
    # ----------------------------------------------------------------------
    summary = ingest_notes(
        parsed_notes=notes,
        client=client,
        dry_run=dry_run,
    )

    # ----------------------------------------------------------------------
    # 5. Print summary for CLI users
    # ----------------------------------------------------------------------
    print("\n=== Ingestion Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    return summary
