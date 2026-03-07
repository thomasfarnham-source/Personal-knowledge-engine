"""
Archetype B chunker — Structured Journal.

Called by chunk_note() in chunker.py when detect_archetype() returns "B".

Structure:
    Long entries of 200-500 words with consistent internal template.
    Template sections: Score, What did I do well, Improvements, Gratitude, etc.
    Retrospective annotations embedded inline — preserved with original entry.

Chunking strategy (not yet implemented):
    Primary split: date stamps.
    Secondary split: template section headers for long entries.
    Retrospective annotations preserved with their original entry.

Metadata:
    - archetype: "B"
"""

from __future__ import annotations

from pke.chunking.chunk import Chunk


def chunk_archetype_b(body: str, created_at: str) -> list[Chunk]:
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
            metadata={"archetype": "B", "status": "placeholder"},
        )
    ]