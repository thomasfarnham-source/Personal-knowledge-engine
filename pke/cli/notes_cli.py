# ==============================
# Notes CLI — Milestone 8
# ==============================
"""
Typer‑based command‑line interface for interacting with notes.

This module is the canonical home of all note‑related CLI commands.
Milestone 8 replaces the legacy argparse/Click implementation with a
modern, modular Typer sub‑application that supports:

    • pke notes upsert <path>
    • --dry-run
    • --verbose
    • --debug

Milestone 8 Overview
--------------------
Milestone 8 is implemented in *layers*, each adding a new stage of the
ingestion pipeline. The steps are:

    Step 1 — Create the Typer CLI scaffold (already completed)
    Step 2 — Load + validate note file
    Step 3 — Generate embedding
    Step 4 — Build Supabase payload
    Step 5 — Supabase upsert + idempotency (future milestone)
    Step 6 — Dry‑run mode (implemented here)

Why Step 1 does not appear in the code
--------------------------------------
Step 1 created this file, the Typer sub‑application, and the basic
`upsert` command stub. It introduced no runtime logic, so there is no
"Step 1" block inside the function. The pipeline begins at Step 2.

Why helpers are labeled “Step 2 Helpers”
----------------------------------------
Pipeline Step 2 (“Load + validate note”) is implemented by two helpers:

    • load_note_file()
    • validate_note_metadata()

These helpers belong to Step 2, which is why they are labeled as such.
The pipeline Step 2 inside `upsert_note()` calls these helpers.

Design Goals
------------
• Provide a clean, contributor‑friendly interface.
• Keep ingestion logic modular and testable.
• Maintain strict idempotency guarantees.
• Support real embedding generation and Supabase writes.
• Provide a safe, deterministic dry‑run mode for debugging.
"""

from pathlib import Path
import json
import typer

# EmbeddingClient is introduced in Milestone 8 Step 3.
from pke.embedding.embedding_client import EmbeddingClient

# ---------------------------------------------------------------------------
# Sub‑application definition (Milestone 8 Step 1)
# ---------------------------------------------------------------------------
# Step 1 created this Typer sub‑application and mounted it under the
# "notes" command group in the root CLI. This scaffold is the foundation
# for all subsequent pipeline steps.
# ---------------------------------------------------------------------------
notes_app = typer.Typer(
    help="Commands for working with notes, including upsert and future operations."
)


# ==============================
# Section 1 — Step 2 Helpers
# ==============================
# These helpers implement the logic for Pipeline Step 2:
#     “Load + validate note file”
# They are separated for clarity, testability, and contributor onboarding.
# ==============================


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
# Section 2 — Milestone 8 (Steps 3–6)
# ==============================
# This section contains:
#   • Step 3 — Embedding generation
#   • Step 4 — Payload construction
#   • Step 6 — Dry‑run execution path
#
# Step 5 (Supabase upsert) will be added in a later milestone.
# ==============================


# ---------------------------------------------------------------------------
# Step 3 Helper: Generate embeddings for note content
# ---------------------------------------------------------------------------
def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for the note content.

    This helper isolates embedding logic so the `upsert` command remains
    focused on orchestration rather than model details.

    Design Notes
    ------------
    • EmbeddingClient abstracts the underlying provider (OpenAI, local model, etc.),
      keeping the CLI decoupled from any specific embedding backend.

    • The function accepts raw text and returns a list[float] representing
      the embedding vector. Dimensionality is determined by the client.

    • Keeping this as a standalone helper makes it easy to:
          - mock during tests
          - swap providers in future milestones
          - centralize error handling if needed
    """
    client = EmbeddingClient()
    return client.embed(text)


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
    primary key (`id`) and required metadata fields.

    Expected Supabase schema (Milestone 8):
        • id: str
        • title: str
        • content: str
        • embedding: list[float]

    Future milestones may add:
        • tags
        • timestamps
        • source metadata
        • chunk references
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
# This command orchestrates the ingestion pipeline. Each Milestone 8 step
# adds a new layer of functionality while keeping the CLI stable,
# testable, and contributor‑friendly.
#
# Pipeline Overview (Milestone 8)
# -------------------------------
#   Step 1 — CLI scaffold (Typer app + command registration)
#   Step 2 — Load + validate note file
#   Step 3 — Generate embedding
#   Step 4 — Build Supabase payload
#   Step 5 — (future) Supabase upsert + idempotency
#   Step 6 — Dry‑run mode (implemented here)
#
# Steps 2–6 are implemented inside this function. Step 1 created the
# command itself and therefore does not appear as runtime logic.
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
        help="Run the full ingestion pipeline but skip the Supabase write.",
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

    Milestone 8 builds this command in layers. Step 6 introduces a complete
    dry‑run execution path that performs all ingestion stages except the
    Supabase write.
    """

    # ============================================================
    # Step 2: Load + validate note
    # ============================================================
    # Error‑Handling Polish (Milestone 8.6.6)
    # --------------------------------------
    # All fatal errors use a consistent "[ERROR]" prefix and exit with code 1.
    # Debug mode prints additional exception details without exposing a full
    # stack trace. This keeps the CLI friendly for contributors while still
    # providing deep visibility when needed.

    path_obj = Path(path)

    try:
        note = load_note_file(path_obj)
        note = validate_note_metadata(note)
    except Exception as e:
        typer.echo(f"[ERROR] {e}")

        if debug:
            typer.echo("[DEBUG] Full exception details:")
            typer.echo(f"{type(e).__name__}: {e}")

        raise typer.Exit(code=1)

    if verbose:
        typer.echo("[INFO] Loaded and validated note.")

    if debug:
        typer.echo("[DEBUG] Note object after parsing/validation:")
        typer.echo(json.dumps(note, indent=2, sort_keys=True))

    # ============================================================
    # Step 3: Generate embedding
    # ============================================================
    embedding = generate_embedding(note["content"])
    note["embedding"] = embedding

    if verbose:
        typer.echo("[INFO] Generated embedding vector.")

    if debug:
        typer.echo(f"[DEBUG] Embedding length: {len(embedding)}")
        typer.echo(f"[DEBUG] Embedding preview: {embedding[:8]} ...")

    # ============================================================
    # Step 4: Build Supabase payload
    # ============================================================
    payload = build_supabase_payload(note)

    if verbose:
        typer.echo("[INFO] Constructed Supabase payload.")

    if debug:
        typer.echo("[DEBUG] Payload object:")
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))

    # ============================================================
    # Step 6: Dry‑run execution path (Milestones 8.6.2–8.6.4)
    # ============================================================
    # Dry‑run mode executes the full ingestion pipeline (Steps 2–4) but
    # intentionally stops before performing any Supabase write. This allows
    # contributors to inspect the final payload safely, without mutating the
    # database or requiring network access.
    #
    # Formatting Notes (8.6.3)
    # ------------------------
    # • The header/footer markers make the payload visually distinct.
    # • json.dumps(..., sort_keys=True) ensures deterministic ordering.
    #
    # Verbose/Debug Integration (8.6.4)
    # ---------------------------------
    # • Verbose mode prints a high‑level message indicating the write was skipped.
    # • Debug mode prints internal state *before* this block, not inside it.
    #
    # Future Milestones
    # -----------------
    # Step 7 will introduce the real Supabase upsert logic, which will run
    # only when dry_run=False.
    # ============================================================
    if dry_run:
        if verbose:
            typer.echo("[DRY RUN] Skipping Supabase write.")

        typer.echo("\n=== DRY RUN: Final Supabase Payload ===")
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        typer.echo("=== END DRY RUN PAYLOAD ===\n")

        typer.echo("[DRY RUN] No changes were sent to Supabase.")
        return

    # ============================================================
    # Step 5 (future): Supabase upsert + idempotency logic
    # ============================================================
    typer.echo("[placeholder] Ready for Supabase upsert (Milestone 8.7+).")
