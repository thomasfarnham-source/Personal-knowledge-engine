"""
ingestion.py

This module contains the ingestion pipeline responsible for taking parsed Evernote/Joplin
notes (from parsed_notes.json) and inserting them into Supabase with embeddings.

Design philosophy:
- Every step is explicit and deterministic.
- No hidden behavior or implicit assumptions.
- Notebook assignment is intentionally simplified to a single canonical notebook
  ("Evernote Import") because the original Evernote structure was flat and Joplin’s
  notebook splitting was an artifact of import batching.
- Metadata is preserved in full for traceability and debugging.
- The ingestion pipeline is intentionally minimal so contributors can reason about it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import the Supabase client used for upserting notes and resolving notebook IDs.
# This keeps ingestion decoupled from the underlying storage implementation.
from pke.supabase_client import SupabaseClient


# ---------------------------------------------------------------------------
# Canonical notebook assignment
# ---------------------------------------------------------------------------
# Evernote originally stored all notes in a single notebook.
# Joplin split the import into multiple notebooks ("My Notes 1", "My Notes 2", ...)
# due to ENEX size and importer batching. These splits have no semantic meaning.
#
# To preserve the *true* structure of the user's data, we assign all notes to a
# single canonical notebook in Supabase. This ensures:
# - deterministic ingestion
# - faithful representation of Evernote’s original structure
# - simpler contributor experience
#
# This constant is intentionally defined at module level so contributors can
# easily locate and modify it if the ingestion strategy changes.
DEFAULT_NOTEBOOK_TITLE = "Evernote Import"


# ---------------------------------------------------------------------------
# ingest_note
# ---------------------------------------------------------------------------
def ingest_note(
    note: Dict[str, Any],
    supabase: SupabaseClient,
    notebook_id: str,
) -> None:
    """
    Ingest a single parsed note into Supabase.

    Parameters
    ----------
    note:
        A dictionary representing a single parsed note from parsed_notes.json.
        The structure originates from Joplin’s sync folder export and includes:
        - title
        - body
        - id, parent_id
        - timestamps
        - source_file
        - resource lists
        - miscellaneous metadata
        Not all fields are guaranteed to exist; ingestion must be defensive.

    supabase:
        An initialized SupabaseClient instance. This object abstracts:
        - notebook resolution
        - embedding generation
        - note upsertion
        Keeping ingestion decoupled from storage logic.

    notebook_id:
        The resolved ID of the canonical notebook ("Evernote Import").
        This is resolved once per batch ingestion to avoid redundant lookups.

    Behavior
    --------
    - Extracts title and body defensively.
    - Skips notes that contain neither title nor body (malformed or empty).
    - Constructs a metadata dictionary preserving all original fields for
      traceability and debugging.
    - Delegates the actual upsert + embedding generation to SupabaseClient.
    """

    # Extract title and body. Use .get() to avoid KeyError if fields are missing.
    # Strip whitespace to avoid storing meaningless titles like "   ".
    title: str = note.get("title", "").strip()
    body: str = note.get("body", "").strip()

    # Skip notes with empty or whitespace-only bodies.
    # Title-only notes are allowed, but body-only notes are the semantic core.
    if not body:
        print(f"Skipping empty-body note: {title}")
        return

    # Construct metadata for traceability.
    # We include the entire raw note so future contributors can debug ingestion
    # without needing to re-open parsed_notes.json.
    metadata: Dict[str, Any] = {
        "source_id": note.get("id"),
        "parent_id": note.get("parent_id"),
        "created_time": note.get("created_time"),
        "updated_time": note.get("updated_time"),
        "source_file": note.get("source_file"),
        "application_data": note.get("application_data"),
        # Full raw note preserved for debugging and reproducibility.
        "raw": note,
    }

    # Delegate the actual insertion + embedding generation to SupabaseClient.
    # This keeps ingestion logic focused on data preparation rather than storage.
    supabase.upsert_note_with_embedding(
        title=title,
        body=body,
        metadata=metadata,
        notebook_id=notebook_id,
    )


# ---------------------------------------------------------------------------
# ingest_all_notes
# ---------------------------------------------------------------------------


def ingest_all_notes(
    parsed_notes_path: Path,
    supabase: SupabaseClient,
) -> None:
    """
    Load parsed_notes.json and ingest all notes into Supabase.

    Parameters
    ----------
    parsed_notes_path:
        Path to parsed_notes.json. This file is expected to contain a list of
        parsed note dictionaries extracted from the Joplin sync folder.

    supabase:
        An initialized SupabaseClient instance.

    Behavior
    --------
    - Loads all parsed notes from disk.
    - Resolves the canonical notebook ID once (important for performance and
      consistency).
    - Iterates through each note and ingests it individually.
    - Delegates note-level ingestion to ingest_note().

    Design Notes
    ------------
    - We intentionally do not parallelize ingestion. Supabase rate limits and
      embedding generation latency make sequential ingestion safer and easier
      to debug.
    - If ingestion is interrupted, re-running the script is safe because
      upsert_note_with_embedding() is idempotent.
    """

    # Load the parsed notes from disk.
    # The file is expected to contain a JSON array of note dictionaries.
    with parsed_notes_path.open("r", encoding="utf-8") as f:
        notes: List[Dict[str, Any]] = json.load(f)

    # Resolve the canonical notebook ID once.
    # resolve_notebook_id() returns Optional[str], so we validate explicitly.
    nid: Optional[str] = supabase.resolve_notebook_id(DEFAULT_NOTEBOOK_TITLE)

    if nid is None:
        # This should never happen because DEFAULT_NOTEBOOK_TITLE is always provided.
        # We fail loudly to avoid silently ingesting notes without a notebook context.
        raise RuntimeError(f"Failed to resolve canonical notebook: {DEFAULT_NOTEBOOK_TITLE!r}")

    notebook_id: str = nid

    # Ingest each note individually.
    for note in notes:
        ingest_note(note, supabase, notebook_id)
