"""
Parser for Joplin-exported Markdown notes.

This module converts a raw .md file (with YAML frontmatter) into a structured
dictionary suitable for ingestion. The parser intentionally returns a rich,
lossless representation of the note so that downstream ingestion stages
(notebook resolution, tag extraction, resource linking, etc.) can operate
deterministically.

The returned dictionary is *not* a NoteRecord yet — it is a parsed note
artifact. The orchestrator later transforms this into a NoteRecord when
calling SupabaseClient.upsert_note_with_embedding().
"""

from datetime import datetime
import os
import re
from typing import Any, Dict, Optional

import frontmatter


def parse_note(filepath: str) -> Dict[str, Any]:
    """
    Parse a single Joplin-exported .md file into a structured dictionary.

    The parser extracts:
        • Core fields: id, title, body
        • Timestamps: created/updated/deleted/user timestamps
        • Joplin metadata: conflict flag, source, markup language
        • Resource references: resource_ids extracted from the body
        • Notebook metadata (if present in frontmatter)
        • Tags (if present in frontmatter)

    Returns:
        A dictionary with stable keys used by the ingestion orchestrator.
    """
    post = frontmatter.load(filepath)
    note_id = os.path.splitext(os.path.basename(filepath))[0]

    # ------------------------------------------------------------
    # Core fields
    # ------------------------------------------------------------
    title: str = post.get("title", "")
    body: str = post.content

    # ------------------------------------------------------------
    # Timestamps (Joplin stores milliseconds since epoch)
    # ------------------------------------------------------------
    created_at = _parse_timestamp(post.get("created_time"))
    updated_at = _parse_timestamp(post.get("updated_time"))
    deleted_time = _parse_timestamp(post.get("deleted_time"))
    user_created_time = _parse_timestamp(post.get("user_created_time"))
    user_updated_time = _parse_timestamp(post.get("user_updated_time"))

    # ------------------------------------------------------------
    # Joplin metadata
    # ------------------------------------------------------------
    is_conflict: bool = post.get("is_conflict", 0) == 1
    source: Optional[str] = post.get("source")
    source_application: Optional[str] = post.get("source_application")
    markup_language: int = post.get("markup_language", 1)

    # ------------------------------------------------------------
    # Notebook + tags (if present in frontmatter)
    # ------------------------------------------------------------
    notebook: Optional[str] = post.get("notebook")
    tags: Optional[list[str]] = post.get("tags")

    # ------------------------------------------------------------
    # Resource references inside the body
    # ------------------------------------------------------------
    resource_ids = re.findall(r":/([a-f0-9]{32})", body)

    return {
        "id": note_id,
        "title": title,
        "body": body,
        "notebook": notebook,
        "tags": tags or [],
        "created_at": created_at,
        "updated_at": updated_at,
        "deleted_time": deleted_time,
        "user_created_time": user_created_time,
        "user_updated_time": user_updated_time,
        "is_conflict": is_conflict,
        "source": source,
        "source_application": source_application,
        "markup_language": markup_language,
        "resource_ids": resource_ids,
    }


def _parse_timestamp(ts: Any) -> Optional[datetime]:
    """
    Convert a Joplin timestamp (milliseconds since epoch) to a datetime object.

    Returns:
        A datetime instance or None if the input is missing or invalid.
    """
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts) / 1000.0)
    except Exception:
        return None