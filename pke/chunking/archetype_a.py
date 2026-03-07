"""
Archetype A chunker — Fragmented Journal.

Called by chunk_note() in chunker.py when detect_archetype() returns "A".

Structure:
    Short entries of 1-10 lines separated by date stamps.
    Date stamps appear on their own line with no consistent heading style.
    No template structure — pure freeform prose per entry.
    High noise tolerance — do not strip content aggressively.

Chunking strategy:
    1. Split body into lines
    2. Walk lines, using is_date_header() to detect entry boundaries
    3. Accumulate lines into the current entry until next date header
    4. When a new date header is found, finalize current entry as a Chunk
    5. Merge any entry under MIN_CHUNK_CHARS (~100 tokens, ~400 chars)
       with its neighbor to avoid creating tiny low-signal chunks
    6. Final entry is finalized at end of body

Timestamps:
    - Extract from the date header line using parse_date()
    - Pass fallback_year extracted from created_at for entries with no year
    - entry_timestamp stored as "YYYY-MM-DD" or None

Chunk text:
    - Include the date header line in the chunk text
    - Do not strip any content — high noise tolerance
    - Strip leading/trailing blank lines from each chunk

Metadata:
    - archetype: "A"
"""

from __future__ import annotations

from typing import Optional

from pke.chunking.chunk import Chunk
from pke.chunking.date_parser import is_date_header, parse_date


def chunk_archetype_a(body: str, created_at: str) -> list[Chunk]:
    """
    Arguments:
        body:       full note body text
        created_at: ISO timestamp string from the note record,
                    used to extract fallback_year for date inference

    Returns:
        list[Chunk]
    """
    MIN_CHUNK_CHARS = 400  # ~100 tokens — merge entries shorter than this

    # Extract fallback year from created_at (e.g. "2019-03-15T00:00:00.000Z" → 2019)
    fallback_year: Optional[int] = None
    if created_at:
        try:
            fallback_year = int(created_at[:4])
        except (ValueError, IndexError):
            fallback_year = None

    lines = body.splitlines()
    raw_entries: list[dict] = []  # list of {lines, timestamp, char_start}

    current_lines: list[str] = []
    current_timestamp: Optional[str] = None
    current_char_start: int = 0
    char_pos: int = 0

    for i, line in enumerate(lines):
        prev_line = lines[i - 1] if i > 0 else ""

        if is_date_header(line, prev_line=prev_line):
            # Finalize previous entry if it has content
            if current_lines:
                raw_entries.append({
                    "lines": current_lines,
                    "timestamp": current_timestamp,
                    "char_start": current_char_start,
                })
            # Start new entry
            current_lines = [line]
            current_timestamp = parse_date(line, fallback_year=fallback_year)
            current_char_start = char_pos
        else:
            current_lines.append(line)

        char_pos += len(line) + 1  # +1 for newline

    # Finalize last entry
    if current_lines:
        raw_entries.append({
            "lines": current_lines,
            "timestamp": current_timestamp,
            "char_start": current_char_start,
        })

    # Merge entries shorter than MIN_CHUNK_CHARS with their next neighbor
    merged_entries: list[dict] = []
    i = 0
    while i < len(raw_entries):
        entry = raw_entries[i]
        text = "\n".join(entry["lines"]).strip()
        if len(text) < MIN_CHUNK_CHARS and i + 1 < len(raw_entries):
            # Merge with next entry — keep earlier timestamp
            next_entry = raw_entries[i + 1]
            merged_lines = entry["lines"] + next_entry["lines"]
            merged_entries.append({
                "lines": merged_lines,
                "timestamp": entry["timestamp"],
                "char_start": entry["char_start"],
            })
            i += 2  # skip next entry — already merged
        else:
            merged_entries.append(entry)
            i += 1

    # Build Chunk objects from merged entries
    chunks: list[Chunk] = []
    for idx, entry in enumerate(merged_entries):
        text = "\n".join(entry["lines"]).strip()
        if not text:
            continue
        char_start = entry["char_start"]
        char_end = char_start + len("\n".join(entry["lines"]))
        chunks.append(
            Chunk(
                chunk_index=idx,
                chunk_text=text,
                char_start=char_start,
                char_end=char_end,
                entry_timestamp=entry["timestamp"],
                metadata={"archetype": "A"},
            )
        )

    # Fall back to single whole-note chunk if no boundaries were detected
    if not chunks:
        chunks = [
            Chunk(
                chunk_index=0,
                chunk_text=body.strip(),
                char_start=0,
                char_end=len(body),
                metadata={"archetype": "A"},
            )
        ]

    return chunks