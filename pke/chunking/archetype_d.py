"""
Archetype D chunker — Travel Journal.

Called by chunk_note() in chunker.py when detect_archetype() returns "D".

Structure:
    Single note per multi-day trip, written in real time.
    Day markers in multiple formats interspersed throughout.
    Images and audio resources inline.
    Broken image placeholders present — strip silently.

Chunking strategy (not yet implemented):
    Primary split: flexible day marker detection.
        Handles: Day N, Day N Title, standalone day names,
        day names in prose, narrative transitions.
    Timestamp strategy (three tiers):
        Tier 1 — explicit date in text → entry_timestamp directly
        Tier 2 — day name/Day N → "calculated: YYYY-MM-DD" from
                 created_at + day offset
        Tier 3 — no marker → entry_timestamp null
    Resource IDs extracted from image and audio links → resource_ids array.
    Resource references stripped from chunk text.
    Broken placeholders stripped silently: {picture) (Picture) (picture) image
    Pre-trip planning block treated as its own reference chunk.

Metadata:
    - archetype: "D"
    - note_type: "travel"
"""

from __future__ import annotations

from pke.chunking.chunk import Chunk


def chunk_archetype_d(body: str, created_at: str) -> list[Chunk]:
    """
    Placeholder — returns single whole-note chunk.
    Real implementation deferred.

    Arguments:
        body:       full note body text
        created_at: ISO timestamp string from the note record,
                    used for calculated date offsets from day markers

    Returns:
        list[Chunk]
    """
    return [
        Chunk(
            chunk_index=0,
            chunk_text=body,
            char_start=0,
            char_end=len(body),
            metadata={
                "archetype": "D",
                "note_type": "travel",
                "status": "placeholder",
            },
        )
    ]