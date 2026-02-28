"""
parse_cli.py

Typer command group for parsing a Joplin Markdown export directory into a
`parsed_notes.json` artifact. This is Stage 1 of the ingestion pipeline.

The pipeline is intentionally split into two stages:

    Stage 1: `pke parse run`
        Parse a Joplin export folder into a structured JSON artifact.

    Stage 2: `pke ingest run`
        Ingest the parsed JSON into Supabase.

This separation allows fast iteration on ingestion without re-parsing
the entire Joplin export each time, and keeps the CLI modular and
contributor-friendly.
"""

import json
import typer
from pathlib import Path

# Correct import based on your actual folder + filename
from pke.parsers.joplin_markdown import parse_joplin_export

# ---------------------------------------------------------------------------
# Create the Typer sub-application for `pke parse`
# ---------------------------------------------------------------------------
parse_app = typer.Typer(
    help=(
        "Stage 1 of the ingestion pipeline.\n\n"
        "Parses a Joplin Markdown export directory into a structured JSON "
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
        help="Path to the Joplin Markdown export directory.",
    ),
    output: Path = typer.Option(
        Path("pke/artifacts/parsed/parsed_notes.json"),
        file_okay=True,
        dir_okay=False,
        writable=True,
        help="Where to write the parsed notes JSON artifact.",
    ),
):
    """
    Parse a Joplin export directory into a structured JSON artifact.

    By default, the parsed notes are written to:

        pke/artifacts/parsed/parsed_notes.json

    This file is the input to Stage 2 of the ingestion pipeline:

        pke ingest run --parsed-path pke/artifacts/parsed/parsed_notes.json

    Use --output to write the artifact to a custom location.
    """
    typer.echo(f"Parsing Joplin export from: {export_path}")

    parsed = parse_joplin_export(str(export_path))

    with output.open("w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2)

    typer.echo(f"Parsed {len(parsed)} notes.")
    typer.echo(f"Output written to: {output}")
