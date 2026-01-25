"""
High-level ingestion orchestrator for parsed Joplin notes.

This module coordinates the full ingestion flow into Supabase:

    1. Notebook resolution and upsert
    2. Note upserts (with embeddings)
    3. Tag extraction and upsert
    4. Note‑tag relationship creation
    5. (future) Resource resolution and uploads

Design goals:

    • Deterministic:
        Given the same parsed input, the orchestrator produces the same final state.

    • Idempotent:
        Safe to run multiple times without creating duplicates or corrupting relationships.

    • Ordered:
        Entities are ingested in a dependency-respecting sequence
        (e.g., notebooks → notes → tags → relationships).

    • Testable:
        Each stage is isolated enough to be unit-tested independently.
"""

from typing import Any, Dict, List

from pke.ingestion.tag_resolution import (
    extract_all_tags,
    map_note_tags_to_ids,
)
from pke.ingestion.notebook_resolution import resolve_notebook_ids
from pke.supabase_client import SupabaseClient


def ingest_notes(
    parsed_notes: List[Dict[str, Any]],
    client: SupabaseClient,
) -> Dict[str, Any]:
    """
    Ingest a batch of parsed notes into Supabase in a deterministic, ordered sequence.

    This function acts as the "brain" of the ingestion pipeline. It does not
    talk directly to Supabase tables; instead, it delegates persistence to
    SupabaseClient and focuses on orchestration, ordering, and high-level
    behavior (e.g., skip logic, summary reporting).

    High-level steps:

        1. Resolve notebook IDs from parsed metadata.
        2. Upsert notebooks so notes can reference them.
        3. Upsert notes (with embeddings) into the `notes` table.
        4. Extract all tags across notes and upsert them into `tags`.
        5. Create note‑tag relationships in the `note_tags` join table.
        6. (future) Resolve and upload resources, then link them to notes.

    Args:
        parsed_notes:
            A list of parsed note dictionaries, typically loaded from
            parsed_notes.json. Each dict is expected to contain fields like:
                - id
                - title
                - body
                - metadata
                - tags (optional)
                - notebook metadata (for resolution)

        client:
            A SupabaseClient instance (real or DummyClient) that implements
            the persistence operations used here (upserts, relationships, etc.).

    Returns:
        A summary dictionary capturing ingestion behavior, including:
            - notes_processed
            - notes_inserted
            - notes_skipped
            - tags_inserted
            - relationships_created
            - failures (list of {id, error})
    """

    # Initialize a structured summary for reporting and testing.
    summary: Dict[str, Any] = {
        "notes_processed": len(parsed_notes),
        "notes_inserted": 0,
        "notes_skipped": 0,
        "tags_inserted": 0,
        "relationships_created": 0,
        "failures": [],
    }

    # ------------------------------------------------------------
    # 1. Resolve notebooks
    # ------------------------------------------------------------
    # Build a mapping of notebook names → metadata extracted from notes.
    notebook_map = resolve_notebook_ids(parsed_notes)

    # Persist notebooks first so notes can reference canonical notebook IDs.
    notebook_id_map = client.upsert_notebooks(notebook_map)

    # ------------------------------------------------------------
    # 2. Upsert notes
    # ------------------------------------------------------------
    for note in parsed_notes:
        try:
            # Skip empty-body notes (e.g., deleted or malformed).
            if not note.get("body"):
                summary["notes_skipped"] += 1
                continue

            # Resolve notebook_id for this note (if any).
            notebook_id = None
            if "notebook" in note:
                notebook_name = note["notebook"]
                notebook_id = notebook_id_map.get(notebook_name)

            # Delegate persistence + embedding generation to the client.
            client.upsert_note_with_embedding(
                title=note.get("title", ""),
                body=note["body"],
                metadata=note.get("metadata", {}),
                id=note.get("id"),
                notebook_id=notebook_id,
            )

            summary["notes_inserted"] += 1

        except Exception as e:
            # Capture failures without halting ingestion.
            summary["failures"].append(
                {
                    "id": note.get("id"),
                    "error": str(e),
                }
            )

    # ------------------------------------------------------------
    # 3. Extract and upsert tags
    # ------------------------------------------------------------
    # Collect all unique tags across all notes.
    all_tags = extract_all_tags(parsed_notes)

    # Upsert tags and receive a mapping of tag_name → tag_id.
    tag_id_map = client.upsert_tags(all_tags)
    summary["tags_inserted"] = len(tag_id_map)

    # ------------------------------------------------------------
    # 4. Create note‑tag relationships
    # ------------------------------------------------------------
    # Build a mapping of note_id → [tag_ids].
    note_tag_map = map_note_tags_to_ids(parsed_notes, tag_id_map)

    # Persist relationships in the join table.
    for note_id, tag_ids in note_tag_map.items():
        client.upsert_note_tag_relationships(note_id, tag_ids)
        summary["relationships_created"] += len(tag_ids)

    # ------------------------------------------------------------
    # 5. (future) Resource ingestion
    # ------------------------------------------------------------
    # Placeholder for future resource ingestion:
    #   • extract resource IDs
    #   • upsert resources
    #   • create note‑resource relationships

    return summary
