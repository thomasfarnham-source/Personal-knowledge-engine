"""
Archetype E chunker — Oral History / Conversation Notes.

Called by chunk_note() in chunker.py when detect_archetype() returns "E".

Structure:
    Sparse text serving as an outline or index to a conversation.
    Audio recordings are the primary content, not supplementary.
    Photos of people or historical documents as supporting evidence.
    Fragmentary sentences — memory triggers, not complete thoughts.
    Single conversation or session per note.

Chunking strategy (not yet implemented):
    Embed whole note if below threshold.
    If above threshold, chunk on audio file boundaries — each recording
    plus surrounding text forms a semantic unit.
    Timestamps extracted from audio filenames (most reliable signal
    in the entire corpus — precise to the second).
    Audio resources flagged as resource_type: audio in metadata.

Timestamp format:
    Extracted from audio filename e.g. "Evernote 20150621 00:15:50.m4a"
    Stored as entry_timestamp: "2015-06-21 00:15:50"

Future:
    Whisper API transcription makes spoken content fully retrievable.
    See milestone 9.x Audio Transcription.

Metadata:
    - archetype: "E"
    - resource_type: "audio"
"""

from __future__ import annotations

from pke.chunking.chunk import Chunk


def chunk_archetype_e(body: str, created_at: str) -> list[Chunk]:
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
            metadata={
                "archetype": "E",
                "resource_type": "audio",
                "status": "placeholder",
            },
        )
    ]