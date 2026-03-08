"""
Archetype E chunker — Oral History / Conversation Notes.

Called by chunk_note() in chunker.py when detect_archetype() returns "E".

Structure:
    Sparse text serving as an outline or index to a conversation.
    Audio recordings are the primary content, not supplementary.
    Photos of people or historical documents as supporting evidence.
    Fragmentary sentences — memory triggers, not complete thoughts.
    Single conversation or session per note.

Chunking strategy:
    1. If body is below threshold, return single whole-note chunk
    2. If above threshold, split on audio file boundaries — each
       recording plus surrounding text forms a semantic unit
    3. Timestamps extracted from audio filenames (most reliable signal
       in the entire corpus — precise to the second)
    4. Resource IDs extracted via resource_extractor.extract_resources()
    5. Resource references stripped from chunk text

Timestamp format:
    Extracted from audio filename e.g. "Evernote 20150621 00:15:50.m4a"
    Stored as entry_timestamp: "2015-06-21 00:15:50"
    Falls back to None if no audio filename timestamp is parseable.

Audio filename timestamp pattern:
     \\d{8}\\s\\d{2}:\\d{2}:\\d{2}  e.g. 20150621 00:15:50

Future:
    Whisper API transcription makes spoken content fully retrievable.
    See milestone 9.x Audio Transcription.

Metadata:
    - archetype: "E"
    - resource_type: "audio"
"""

from __future__ import annotations

import re
from typing import Optional

from pke.chunking.chunk import Chunk
from pke.chunking.resource_extractor import ResourceResult, extract_resources

# Audio link pattern — used to detect chunk boundaries
_AUDIO_LINK_RE = re.compile(
    r"\[.*?\.(m4a|mp3|wav)\]\(:/([a-f0-9]+)\)",
    re.IGNORECASE,
)

# Audio filename timestamp pattern: 20150621 00:15:50
_AUDIO_TIMESTAMP_RE = re.compile(r"(\d{4})(\d{2})(\d{2})\s(\d{2}:\d{2}:\d{2})")

MIN_CHUNK_CHARS = 400  # ~100 tokens — merge chunks shorter than this


def _extract_audio_timestamp(line: str) -> Optional[str]:
    """
    Extract a precise timestamp from an audio filename link line.

    Looks for pattern: 20150621 00:15:50 in the link text.
    Returns "2015-06-21 00:15:50" or None if not found.
    """
    match = _AUDIO_TIMESTAMP_RE.search(line)
    if match:
        year, month, day, time = match.groups()
        return f"{year}-{month}-{day} {time}"
    return None


def chunk_archetype_e(body: str, created_at: str) -> list[Chunk]:
    """
    Split on audio file boundaries. Extract timestamps from audio
    filenames. Strip resource references from chunk text.
    Falls back to single whole-note chunk if no audio boundaries
    detected or body is below threshold.

    Arguments:
        body:       full note body text
        created_at: ISO timestamp string from the note record

    Returns:
        list[Chunk]
    """
    lines = body.splitlines()
    raw_entries: list[dict] = []

    current_lines: list[str] = []
    current_char_start: int = 0
    current_timestamp: Optional[str] = None
    char_pos: int = 0
    found_first_audio: bool = False

    for line in lines:
        if _AUDIO_LINK_RE.search(line):
            # Finalize previous entry if it has content
            if current_lines:
                raw_entries.append(
                    {
                        "lines": current_lines,
                        "char_start": current_char_start,
                        "timestamp": current_timestamp,
                        "is_preamble": not found_first_audio,
                    }
                )
            found_first_audio = True
            # Start new entry with this audio line included
            current_lines = [line]
            current_char_start = char_pos
            current_timestamp = _extract_audio_timestamp(line)
        else:
            current_lines.append(line)

        char_pos += len(line) + 1

    # Finalize last entry
    if current_lines:
        raw_entries.append(
            {
                "lines": current_lines,
                "char_start": current_char_start,
                "timestamp": current_timestamp,
                "is_preamble": not found_first_audio,
            }
        )

    # Merge entries shorter than MIN_CHUNK_CHARS with next neighbor
    merged_entries: list[dict] = []
    i = 0
    while i < len(raw_entries):
        entry = raw_entries[i]
        text = "\n".join(entry["lines"]).strip()
        next_exists = i + 1 < len(raw_entries)
        if (
            len(text) < MIN_CHUNK_CHARS
            and not entry["is_preamble"]
            and next_exists
            and not raw_entries[i + 1]["is_preamble"]
        ):
            next_entry = raw_entries[i + 1]
            merged_entries.append(
                {
                    "lines": entry["lines"] + next_entry["lines"],
                    "char_start": entry["char_start"],
                    "timestamp": entry["timestamp"],  # keep earlier timestamp
                    "is_preamble": False,
                }
            )
            i += 2
        else:
            merged_entries.append(entry)
            i += 1

    # Build Chunk objects
    chunks: list[Chunk] = []
    for idx, entry in enumerate(merged_entries):
        raw_text = "\n".join(entry["lines"])

        # Extract resource IDs and strip references from chunk text
        result: ResourceResult = extract_resources(raw_text)
        clean_text = result.clean_text
        resource_ids = result.resource_ids

        if not clean_text:
            continue

        char_start = entry["char_start"]
        char_end = char_start + len(raw_text)

        metadata: dict = {"archetype": "E", "resource_type": "audio"}
        if entry["is_preamble"]:
            metadata["preamble"] = True

        chunks.append(
            Chunk(
                chunk_index=idx,
                chunk_text=clean_text,
                char_start=char_start,
                char_end=char_end,
                entry_timestamp=entry["timestamp"],
                resource_ids=resource_ids,
                metadata=metadata,
            )
        )

    # Fall back to single whole-note chunk if no audio boundaries detected
    if not chunks:
        chunks = [
            Chunk(
                chunk_index=0,
                chunk_text=body.strip(),
                char_start=0,
                char_end=len(body),
                metadata={"archetype": "E", "resource_type": "audio"},
            )
        ]

    return chunks
