"""
Archetype C chunker — Reference / Medical Log.

Called by chunk_note() in chunker.py when detect_archetype() returns "C".

Structure:
    Undated opening block describing current state (most retrieval-valuable).
    Followed by dated log entries appended over time.
    Embedded sub-tables (e.g. injection schedules) interspersed in log.

Chunking strategy (not yet implemented):
    Undated opening section → own reference chunk.
    Dated log entries → split on date stamps.
    Embedded sub-tables → kept intact, not split on internal dates.

Metadata:
    - archetype: "C"
"""

from __future__ import annotations

from pke.chunking.chunk import Chunk


def chunk_archetype_c(body: str, created_at: str) -> list[Chunk]:
    """
    Placeholder — returns single whole-note chunk.
    Real implementation deferred.

    Arguments:
        body:       full note body text
        created_at: ISO timestamp string from the note record

    Returns:
        list[Chunk]
    """
    return [
        Chunk(
            chunk_index=0,
            chunk_text=body,
            char_start=0,
            char_end=len(body),
            metadata={"archetype": "C", "status": "placeholder"},
        )
    ]