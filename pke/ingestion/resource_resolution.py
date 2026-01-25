"""
resource_resolution.py

Resource (attachment) extraction and upsert logic used during the ingestion
pipeline. Notes may reference external resources (images, PDFs, attachments)
via parsed metadata. This module provides two lightweight helpers:

1. extract_resources(note)
   - Reads resource identifiers from a parsed note dictionary.
   - Called early in the ingestion flow, before note upsertion.

2. upsert_resources(client, resources)
   - Inserts or resolves resource records in Supabase.
   - Currently implemented as a stub so ingestion can proceed without
     full resource handling. In dry‑run mode, deterministic fake IDs
     are returned; in real mode, no-op behavior returns an empty list.

These stubs allow the ingestion pipeline to remain structurally complete
while resource handling is implemented incrementally.
"""

from typing import Any, Dict, List


def extract_resources(note: Dict[str, Any]) -> List[str]:
    """
    Extract resource identifiers from a parsed note dictionary.

    A parsed note produced by parse_note() may contain a "resource_ids" field
    listing attachment identifiers extracted from the Markdown body. These
    identifiers correspond to Joplin resource IDs (32‑character hex strings).

    Args:
        note:
            Parsed note dictionary.

    Returns:
        A list of resource IDs. Returns an empty list if the note does not
        declare any resources.

    Notes:
        This function is called early in the ingestion pipeline so the
        orchestrator can collect all resources that may need to be inserted
        or resolved before note upsertion.
    """
    return note.get("resource_ids", [])


def upsert_resources(client: Any, resources: List[str]) -> List[Dict[str, str]]:
    """
    Insert or resolve resources in Supabase.

    Args:
        client:
            The Supabase client wrapper. Must expose a `dry_run` attribute
            used to determine whether to return deterministic fake IDs.
            Full resource upsert logic will be implemented later.

        resources:
            A list of resource identifiers extracted from a note.

    Returns:
        In dry‑run mode:
            A list of deterministic fake resource records of the form:
                {"id": "dry-resource-<resource_id>"}

        In real mode:
            An empty list until full resource handling is added.

    Notes:
        This function is invoked after extract_resources() during ingestion.
        It ensures the pipeline remains structurally complete even before
        resource storage, hashing, or deduplication logic is implemented.
    """
    if getattr(client, "dry_run", False):
        # Deterministic fake IDs allow the ingestion pipeline to proceed
        # without requiring real resource uploads.
        return [{"id": f"dry-resource-{r}"} for r in resources]

    # Real implementation will insert or resolve resources in Supabase.
    return []
