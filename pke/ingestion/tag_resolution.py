"""
Tag extraction, normalization, and relationship mapping.

This module provides pure helper functions used by the ingestion orchestrator.
These functions never touch Supabase directly — they only transform parsed
note data into deterministic structures that the orchestrator can pass to
SupabaseClient.

Design goals:
    • Pure functions (no side effects)
    • Deterministic output
    • Contributor‑friendly and easy to test
    • Normalized tag names (trimmed, non‑empty)
"""

from typing import Any, Dict, List, Mapping, Set


# ---------------------------------------------------------------------------
# Extract all tag names across parsed notes
# ---------------------------------------------------------------------------
def extract_all_tags(parsed_notes: List[Mapping[str, Any]]) -> Set[str]:
    """
    Extract the set of all unique, normalized tag names from parsed notes.

    Normalization rules:
        • Ignore None or empty strings
        • Strip whitespace
        • Deduplicate (returns a set)

    Args:
        parsed_notes:
            A list of parsed note dictionaries produced by parse_note().

    Returns:
        A set of unique tag strings.
    """
    tags: Set[str] = set()

    for note in parsed_notes:
        for tag in note.get("tags", []) or []:
            if not tag:
                continue
            normalized = tag.strip()
            if normalized:
                tags.add(normalized)

    return tags


# ---------------------------------------------------------------------------
# Map note → tag UUIDs
# ---------------------------------------------------------------------------
def map_note_tags_to_ids(
    parsed_notes: List[Mapping[str, Any]],
    tag_id_map: Mapping[str, str],
) -> Dict[str, List[str]]:
    """
    Convert tag strings on each note into canonical tag UUIDs.

    Example:
        note.tags = ["python", "cli"]
        tag_id_map = {"python": "uuid1", "cli": "uuid2"}

    Produces:
        {"note_id": ["uuid1", "uuid2"]}

    Rules:
        • Only tags present in tag_id_map are included.
        • Notes without tags produce an empty list.
        • Notes without an "id" are skipped entirely.
        • Tag names are normalized (strip whitespace).

    Args:
        parsed_notes:
            Parsed note dictionaries from parse_note().

        tag_id_map:
            Mapping of tag_name → tag_id returned by SupabaseClient.upsert_tags().

    Returns:
        A mapping of note_id → list of tag UUIDs.
    """
    note_tag_map: Dict[str, List[str]] = {}

    for note in parsed_notes:
        note_id = note.get("id")
        if not note_id:
            continue

        tag_names = note.get("tags", []) or []
        tag_ids: List[str] = []

        for name in tag_names:
            if not name:
                continue
            normalized = name.strip()
            if not normalized:
                continue
            tag_id = tag_id_map.get(normalized)
            if tag_id:
                tag_ids.append(tag_id)

        if tag_ids:
            note_tag_map[note_id] = tag_ids

    return note_tag_map
