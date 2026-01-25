"""
Command‑line interface for interacting with notes.

This module now implements the Milestone 8 Typer‑based CLI.

Previous versions of this file used argparse and operated on
`parsed_notes.json` as a staging artifact. Milestone 8 replaces that
approach with a modern, modular Typer sub‑application that supports:

    • notes upsert <path>
    • --dry-run
    • --verbose
    • --debug

The goal is to provide a clean, contributor‑friendly interface that
supports real Supabase upserts, embedding generation, and idempotency.
"""

from pathlib import Path
import json
import typer

# ---------------------------------------------------------------------------
# Sub‑application definition
# ---------------------------------------------------------------------------
# Typer allows us to structure the CLI into logical groups. The main CLI
# (defined in pke/cli/main.py) imports and registers this sub‑app under
# the command group "notes", giving us:
#
#       pke notes <command>
#
# This keeps the CLI modular and avoids cluttering the root namespace.
# ---------------------------------------------------------------------------
notes_app = typer.Typer(
    help="Commands for working with notes, including upsert and future operations."
)


# ---------------------------------------------------------------------------
# Step 2 Helper: Load a note file from disk
# ---------------------------------------------------------------------------
def load_note_file(path: Path) -> dict:
    """
    Load a note file from disk and parse it into a Python dictionary.

    Milestone 8 assumption:
        • Notes are JSON files produced by the ingestion pipeline.
        • Markdown and other formats will be supported in later milestones.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the file contains invalid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(f"Note file not found: {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in note file: {path}") from e


# ---------------------------------------------------------------------------
# Step 2 Helper: Validate required metadata fields
# ---------------------------------------------------------------------------
def validate_note_metadata(note: dict) -> dict:
    """
    Validate that the note contains required metadata fields.

    Required fields for Milestone 8:
        • id
        • title
        • content

    Optional (future milestones):
        • tags
        • created_at
        • updated_at

    Returns
    -------
    dict
        The validated note object.

    Raises
    ------
    ValueError
        If required fields are missing.
    """
    required = ["id", "title", "content"]
    missing = [field for field in required if field not in note]

    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    return note


# ---------------------------------------------------------------------------
# Command: notes upsert <path>
# ---------------------------------------------------------------------------
# This is the Milestone 8 entrypoint. It replaces the old argparse‑based
# `upsert <note_id>` command with a file‑based workflow:
#
#       pke notes upsert path/to/note.json
#
# The command accepts:
#   • path      — required positional argument
#   • --dry-run — parse + embed + build payload, but do NOT write to Supabase
#   • --verbose — show high‑level progress logs
#   • --debug   — show full payloads, responses, and timing information
#
# Step 2 adds:
#   • file loading
#   • metadata validation
#
# Later milestones will add:
#   • embedding generation
#   • Supabase upsert
#   • idempotency logic
# ---------------------------------------------------------------------------
@notes_app.command("upsert")
def upsert_note(
    path: str = typer.Argument(
        ...,
        help="Path to the note file to upsert (JSON for Milestone 8).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run end‑to‑end without writing to Supabase.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show high‑level progress logs.",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Show full debug output including payloads and timings.",
    ),
) -> None:
    """
    Upsert a note into Supabase, generating embeddings and ensuring idempotency.

    Step 2 implementation:
        • load the note file
        • validate required metadata
        • optionally print debug output

    Steps 3–10 will progressively fill in the real behavior.
    """
    path_obj = Path(path)

    # -----------------------------
    # Step 2: Load + validate note
    # -----------------------------
    try:
        note = load_note_file(path_obj)
        note = validate_note_metadata(note)
    except Exception as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)

    if verbose:
        typer.echo("Loaded and validated note successfully.")

    if debug:
        typer.echo("Note object after parsing/validation:")
        typer.echo(json.dumps(note, indent=2))

    # Placeholder for upcoming steps
    typer.echo("[placeholder] Ready for embedding + upsert pipeline.")
    typer.echo(f"  dry_run={dry_run}, verbose={verbose}, debug={debug}")
