# ==============================
# Section 1 for review purposes
# ==============================
"""
Command‑line interface for interacting with notes.

This module implements the Milestone 8 Typer‑based CLI.

Background
----------
Earlier versions of this project used argparse and operated on a
`parsed_notes.json` staging artifact. That approach worked during early
experiments but became brittle as the ingestion pipeline matured.

Milestone 8 replaces that legacy design with a modern, modular Typer
sub‑application that supports:

    • pke notes upsert <path>
    • --dry-run
    • --verbose
    • --debug

Design Goals
------------
• Provide a clean, contributor‑friendly interface.
• Support real Supabase upserts and embedding generation.
• Maintain strict idempotency guarantees.
• Keep the CLI modular so new note‑related commands can be added
  without cluttering the root namespace.
"""

from pathlib import Path
import json
import typer

# EmbeddingClient is introduced in Milestone 8 Step 3.
# Importing it here keeps all dependencies visible at the top of the module.
from pke.embedding import EmbeddingClient

# Supabase client is introduced in Milestone 8 Step 5.
# This import is intentionally placed here so all external dependencies
# remain visible and discoverable at the top of the module.
from pke.supabase_client import SupabaseClient

# ---------------------------------------------------------------------------
# Sub‑application definition
# ---------------------------------------------------------------------------
# Typer allows the CLI to be organized into logical groups. The main CLI
# (defined in pke/cli/main.py) mounts this sub‑app under the "notes"
# command group, giving us:
#
#       pke notes <command>
#
# This structure keeps the root CLI clean and makes it easy for future
# contributors to add new note‑related commands (e.g., list, preview,
# search, sync) without modifying unrelated parts of the system.
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


# ==============================
# Section 2 - For Review purposes
# ===============================


# ---------------------------------------------------------------------------
# Step 3 Helper: Generate embeddings for note content
# ---------------------------------------------------------------------------
def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for the note content.

    This helper isolates the embedding logic so the `upsert` command
    remains clean and focused on orchestration rather than model details.

    Design Notes
    ------------
    • EmbeddingClient abstracts the underlying provider (OpenAI, local model, etc.),
      keeping the CLI decoupled from any specific embedding backend.

    • The function accepts raw text and returns a list[float] representing
      the embedding vector. The dimensionality is determined by the client.

    • Keeping this as a standalone helper makes it easy to:
          - mock during tests
          - swap providers in the future
          - centralize error handling if needed
    """

    # Instantiate the embedding client.
    # IMPORTANT:
    # We name this `embedding_client` to avoid colliding with the Supabase client
    # used later in the upsert pipeline. Previously this was named `client`,
    # which caused an undefined-name error when the upsert step attempted to call
    # `client.upsert_note(...)`. Using a distinct variable name prevents that.
    embedding_client = EmbeddingClient()

    # Generate and return the embedding vector for the provided text.
    # The deterministic provider ensures reproducible behavior during development.
    return embedding_client.embed(text)


# ===============================
# Section 2 - for review purposes
# ===============================
# ---------------------------------------------------------------------------
# Step 4 Helper: Build Supabase payload
# ---------------------------------------------------------------------------
def build_supabase_payload(note: dict) -> dict:
    """
    Construct the payload object expected by the Supabase `notes` table.

    This function isolates schema decisions so the CLI remains stable even
    if the backend evolves. It also ensures idempotency by including the
    primary key (`id`) and any required metadata fields.

    Expected Supabase schema (Milestone 8):
        • id: str
        • title: str
        • content: str
        • embedding: list[float]

    Future milestones may add:
        • tags
        • created_at / updated_at
        • source metadata
        • chunk references

    Returns
    -------
    dict
        A clean, schema‑aligned payload ready for upsert.
    """
    return {
        "id": note["id"],
        "title": note["title"],
        "content": note["content"],
        "embedding": note["embedding"],
    }


# ---------------------------------------------------------------------------
# Command: notes upsert <path>
# ---------------------------------------------------------------------------
# Milestone 8 end‑to‑end ingestion entrypoint.
#
# This replaces the old argparse‑based `upsert <note_id>` command with a
# file‑driven workflow:
#
#       pke notes upsert path/to/note.json
#
# The command accepts:
#   • path      — required positional argument (JSON note file)
#   • --dry-run — run full pipeline (parse → embed → payload) but skip DB write
#   • --verbose — show high‑level progress logs for each pipeline stage
#   • --debug   — show full objects, payloads, and Supabase responses
#
# Milestone 8 is implemented incrementally:
#
#   Step 2 — Load + validate note metadata
#       • read JSON file from disk
#       • validate required metadata fields
#       • emit verbose/debug output
#
#   Step 3 — Embedding generation
#       • compute embedding vector from note["content"]
#       • attach embedding to note object
#       • emit verbose/debug output
#
#   Step 4 — Payload construction
#       • build schema‑aligned Supabase payload
#       • emit verbose/debug output
#
#   Step 5 — Supabase upsert (new in this milestone)
#       • skip if --dry-run is set
#       • call SupabaseClient.upsert_note(payload)
#       • emit verbose/debug output
#
# Later milestones (6–10) will add:
#       • idempotency logic
#       • tag relationship upserts
#       • notebook resolution
#       • full debug tracing
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
    Upsert a note into Supabase, generating embeddings and constructing a
    schema‑aligned payload. This command is built incrementally across
    Milestone 8, with each step adding a new stage of the ingestion pipeline.

    Step 2 responsibilities:
        • load the note file from disk
        • validate required metadata fields
        • optionally print verbose/debug output

    Step 3 responsibilities:
        • generate an embedding vector for the note content

    Step 4 responsibilities:
        • construct the Supabase payload

    Step 5 responsibilities:
        • perform the Supabase upsert (unless --dry-run is set)
        • surface Supabase response via verbose/debug output

    Future steps (6–10):
        • idempotency logic
        • tag relationship upserts
        • notebook resolution
        • full debug tracing
    """
    # Instantiate clients at the top of the function body
    supabase = SupabaseClient()

    # Convert raw string path into a Path object for safer filesystem work.
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

    # -----------------------------
    # Step 3: Generate embedding
    # -----------------------------
    embedding = generate_embedding(note["content"])
    note["embedding"] = embedding

    if verbose:
        typer.echo("Generated embedding vector.")

    if debug:
        typer.echo(f"Embedding length: {len(embedding)}")
        typer.echo(f"Embedding preview: {embedding[:8]} ...")

    # -----------------------------
    # Step 4: Build Supabase payload
    # -----------------------------
    payload = build_supabase_payload(note)

    if verbose:
        typer.echo("Constructed Supabase payload.")

    if debug:
        typer.echo("Payload object:")
        typer.echo(json.dumps(payload, indent=2))

    # -----------------------------
    # Step 5: Supabase upsert
    # -----------------------------
    if dry_run:
        # Dry‑run mode: pipeline runs fully but does NOT write to Supabase.
        typer.echo("[dry-run] Skipping Supabase upsert.")
        return

    # Perform the actual upsert.
    result = supabase.upsert_note(payload)

    if verbose:
        typer.echo("Supabase upsert completed.")

    if debug:
        typer.echo("Returned row from Supabase:")
        typer.echo(json.dumps(result, indent=2))
