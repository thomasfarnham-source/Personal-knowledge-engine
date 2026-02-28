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
from typing import Any, Dict, Optional, List

import frontmatter

# General resource pattern used by Joplin: :/<hex-string>
# Tests expect *any* hex length, not only 32 chars.
RESOURCE_RE = re.compile(r":/([a-fA-F0-9]+)")


# ============================================================================
# 1 — PARSE A SINGLE NOTE
# ============================================================================


def parse_note(filepath: str) -> Dict[str, Any]:
    """
    Parse a single Joplin-exported .md file into a structured dictionary.

    The parser extracts:
        • Core fields: id, title, body
        • Timestamps: created/updated/deleted/user timestamps (ms since epoch)
        • Joplin metadata: conflict flag, source, markup language
        • Resource references: extracted from Markdown body
        • Notebook metadata (if present in frontmatter)
        • Tags (if present in frontmatter)

    Returns:
        A dictionary with stable keys used by the ingestion orchestrator.
    """

    # Load YAML frontmatter + Markdown body using python-frontmatter.
    post = frontmatter.load(filepath)

    # Prefer explicit Joplin-exported IDs from YAML frontmatter.
    note_id = post.metadata.get("id") or os.path.splitext(os.path.basename(filepath))[0]

    # ------------------------------------------------------------
    # Core fields
    # ------------------------------------------------------------
    title: str = post.metadata.get("title", "")
    body: str = post.content

    # ------------------------------------------------------------
    # Timestamps (raw ms integers — no conversion)
    # ------------------------------------------------------------
    created_time = post.metadata.get("created_time")
    updated_time = post.metadata.get("updated_time")
    deleted_time = post.metadata.get("deleted_time")
    user_created_time = post.metadata.get("user_created_time")
    user_updated_time = post.metadata.get("user_updated_time")

    # ------------------------------------------------------------
    # Joplin metadata
    # ------------------------------------------------------------
    is_conflict: bool = post.metadata.get("is_conflict", 0) == 1
    source: Optional[str] = post.metadata.get("source")
    source_application: Optional[str] = post.metadata.get("source_application")
    markup_language: int = post.metadata.get("markup_language", 1)

    # ------------------------------------------------------------
    # Notebook + tags (if present)
    # NOTE:
    #   Joplin Markdown exports *do not* include notebook names.
    #   This will usually be None, which is correct.
    # ------------------------------------------------------------
    notebook: Optional[str] = post.metadata.get("notebook")
    tags = post.metadata.get("tags", [])

    # ------------------------------------------------------------
    # Resource references inside the body
    # ------------------------------------------------------------
    resources = RESOURCE_RE.findall(body)

    # ------------------------------------------------------------
    # Final structured dictionary
    # ------------------------------------------------------------
    return {
        "id": note_id,
        "title": title,
        "body": body,
        "notebook": notebook,
        "tags": tags,
        "created_time": created_time,
        "updated_time": updated_time,
        "deleted_time": deleted_time,
        "user_created_time": user_created_time,
        "user_updated_time": user_updated_time,
        "is_conflict": is_conflict,
        "source": source,
        "source_application": source_application,
        "markup_language": markup_language,
        "resources": resources,
    }


# ============================================================================
# 2 — PARSE AN ENTIRE JOPLIN EXPORT FOLDER
# ============================================================================


def parse_joplin_export(folder_path: str) -> List[Dict[str, Any]]:
    """
    Parse all Joplin-exported Markdown notes in a folder.

    This function:
        • walks the folder
        • finds all .md files
        • parses each using parse_note()
        • returns a list of parsed note dictionaries

    It does NOT:
        • modify existing parse_note() behavior
        • assume anything about notebook structure
        • touch the _resources/ folder (handled later by orchestrator)

    Returns:
        A list of parsed note dictionaries.
    """

    notes: List[Dict[str, Any]] = []

    for filename in os.listdir(folder_path):
        if filename.lower().endswith(".md"):
            full_path = os.path.join(folder_path, filename)
            notes.append(parse_note(full_path))

    return notes


# ============================================================================
# 3 — LEGACY TIMESTAMP HELPER (unused by parse_note)
# ============================================================================


def _parse_timestamp(ts: Any) -> Optional[datetime]:
    """
    Legacy helper for converting Joplin timestamps (ms since epoch)
    into datetime objects.

    NOTE:
        The current test suite expects *raw millisecond integers*,
        so this helper is no longer used by parse_note(). It is kept
        for future ingestion stages that may require datetime objects.
    """
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts) / 1000.0)
    except Exception:
        return None
