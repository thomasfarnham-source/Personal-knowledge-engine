"""
Tag extraction, normalization, and relationship mapping.

This module provides pure helper functions used by the ingestion orchestrator.
These functions never touch Supabase directly — they only transform parsed
note data into deterministic structures that the orchestrator can pass to
SupabaseClient.

The design is intentionally simple and testable:
    • extract_all_tags() flattens tag lists across notes
    • map_note_tags_to_ids() converts tag strings → canonical UUIDs
"""

from typing import Any, Dict, List


def extract_all_tags(parsed_notes: List[Dict[str, Any]]) -> List[str]:
    """
    Extract all tag strings across all notes.

    Current behavior:
        • Look for note["tags"] (set by parse_note)
        • Flatten all tag lists into a single list
        • No normalization or deduplication here — SupabaseClient handles that

    Args:
        parsed_notes:
            A list of parsed note dictionaries produced by parse_note().

    Returns:
        A flat list of tag strings (may contain duplicates).
    """
    all_tags: List[str] = []

    for note in parsed_notes:
        tags = note.get("tags", [])
        all_tags.extend(tags)

    return all_tags


def map_note_tags_to_ids(
    parsed_notes: List[Dict[str, Any]],
    tag_id_map: Dict[str, str],
) -> Dict[str, List[str]]:
    """
    Convert tag strings on each note into canonical tag UUIDs.

    Example:
        note.tags = ["python", "cli"]
        tag_id_map = {"python": "uuid1", "cli": "uuid2"}

    Produces:
        {"note_id": ["uuid1", "uuid2"]}

    Notes:
        • Only tags present in tag_id_map are included.
        • Notes without tags produce an empty list.
        • Notes without an "id" are skipped entirely.

    Args:
        parsed_notes:
            Parsed note dictionaries from parse_note().

        tag_id_map:
            Mapping of tag_name → tag_id returned by SupabaseClient.upsert_tags().

    Returns:
        A mapping of note_id → list of tag UUIDs.
    """
    result: Dict[str, List[str]] = {}

    for note in parsed_notes:
        note_id = note.get("id")
        if not note_id:
            continue

        tag_strings = note.get("tags", [])
        tag_ids = [tag_id_map[t] for t in tag_strings if t in tag_id_map]

        result[note_id] = tag_ids

    return result
