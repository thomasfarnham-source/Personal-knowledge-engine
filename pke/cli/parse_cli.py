"""
parse_cli.py

Typer command group for parsing a Joplin sync folder directory into a
`parsed_notes.json` artifact. This is Stage 1 of the ingestion pipeline.

The pipeline is intentionally split into two stages:

    Stage 1: `pke parse run`
        Parse a Joplin sync-folder into a structured JSON artifact.

    Stage 2: `pke ingest run`
        Ingest the parsed JSON into Supabase.

This separation allows fast iteration on ingestion without re-parsing
the entire Joplin export each time, and keeps the CLI modular and
contributor-friendly.
"""

import json
import typer
from pathlib import Path

# Canonical parser for the Joplin sync folder (stage 1)
from pke.parsers.joplin_sync_parser import parse_sync_folder

# ---------------------------------------------------------------------------
# Create the Typer sub-application for `pke parse`
# ---------------------------------------------------------------------------
parse_app = typer.Typer(
    help=(
        "Stage 1 of the ingestion pipeline.\n\n"
        "Parses a Joplin sync-folder directory into a structured JSON "
        "artifact. The default output location is:\n\n"
        "    pke/artifacts/parsed/parsed_notes.json\n\n"
        "This artifact is consumed by Stage 2:\n\n"
        "    pke ingest run --parsed-path pke/artifacts/parsed/parsed_notes.json\n\n"
        "Use --output to override the destination."
    )
)


# ---------------------------------------------------------------------------
# `pke parse run`
# ---------------------------------------------------------------------------
@parse_app.command("run")
def parse_run(
    export_path: Path = typer.Option(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Path to the Joplin sync-folder directory.",
    ),
    output: Path = typer.Option(
        Path("pke/artifacts/parsed/parsed_notes.json"),
        file_okay=True,
        dir_okay=False,
        writable=True,
        help="Where to write the parsed notes JSON artifact.",
    ),
) -> None:
    """
    Parse a Joplin sync-folder directory into a structured JSON artifact.

    By default, the parsed notes are written to:

        pke/artifacts/parsed/parsed_notes.json

    This file is the input to Stage 2 of the ingestion pipeline:

        pke ingest run --parsed-path pke/artifacts/parsed/parsed_notes.json

    Use --output to write the artifact to a custom location.
    """
    typer.echo(f"Parsing Joplin sync-folder from: {export_path}")

    parsed = parse_sync_folder(Path(export_path))

    with output.open("w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2)

    typer.echo(f"Parsed {len(parsed)} notes.")
    typer.echo(f"Output written to: {output}")
