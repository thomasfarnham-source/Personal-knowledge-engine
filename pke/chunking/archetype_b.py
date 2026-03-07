"""
Archetype B chunker — Structured Journal.

Called by chunk_note() in chunker.py when detect_archetype() returns "B".

Structure:
    Long entries of 200-500 words with consistent internal template.
    Template sections: Score, What did I do well, Improvements, Gratitude, etc.
    Retrospective annotations embedded inline — preserved with original entry.
    Each entry is separated by a date stamp header.

Chunking strategy:
    1. Split on date stamp boundaries using is_date_header()
    2. For entries that exceed MAX_CHUNK_CHARS, apply secondary split
       on template section headers within the entry
    3. Retrospective annotations (lines starting with "##" that follow
       an entry and reference it) are kept with their original entry,
       not split into a separate chunk
    4. Merge any entry under MIN_CHUNK_CHARS with its next neighbor

Timestamps:
    - Extract from date header line using parse_date()
    - Pass fallback_year extracted from created_at
    - entry_timestamp stored as "YYYY-MM-DD" or None

Chunk text:
    - Include the date header line in the chunk text
    - Preserve template section headers within chunks
    - Strip leading/trailing blank lines from each chunk

Metadata:
    - archetype: "B"
"""

from __future__ import annotations

import re
from typing import Optional

from pke.chunking.chunk import Chunk
from pke.chunking.date_parser import is_date_header, parse_date

# Template section header pattern — matches known structured journal headers
TEMPLATE_HEADER_RE = re.compile(
    r"^#{1,3}\s*(?:Score|What did I do well|Improvements|Gratitude"
    r"|Intentions|Goals|Summary|Notes)\b",
    re.IGNORECASE,
)

MIN_CHUNK_CHARS = 400   # ~100 tokens — merge entries shorter than this
MAX_CHUNK_CHARS = 2000  # ~500 tokens — split entries longer than this


def chunk_archetype_b(body: str, created_at: str) -> list[Chunk]:
    """
    Split on date stamp boundaries. For long entries, apply secondary
    split on template section headers. Merge short entries with neighbors.
    Falls back to single whole-note chunk if no boundaries detected.

    Arguments:
        body:       full note body text
        created_at: ISO timestamp string from the note record,
                    used to extract fallback_year for date inference

    Returns:
        list[Chunk]
    """
    # Extract fallback year from created_at
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

    # Secondary split: break long entries on template section headers
    split_entries: list[dict] = []
    for entry in raw_entries:
        text = "\n".join(entry["lines"]).strip()
        if len(text) <= MAX_CHUNK_CHARS:
            split_entries.append(entry)
            continue

        # Split this entry on template section headers
        section_lines: list[str] = []
        section_char_start = entry["char_start"]
        section_timestamp = entry["timestamp"]
        section_char_pos = entry["char_start"]

        for line in entry["lines"]:
            if TEMPLATE_HEADER_RE.match(line) and section_lines:
                # Finalize current section
                split_entries.append({
                    "lines": section_lines,
                    "timestamp": section_timestamp,
                    "char_start": section_char_start,
                })
                # Start new section — inherit timestamp from parent entry
                section_lines = [line]
                section_char_start = section_char_pos
            else:
                section_lines.append(line)
            section_char_pos += len(line) + 1

        # Finalize last section
        if section_lines:
            split_entries.append({
                "lines": section_lines,
                "timestamp": section_timestamp,
                "char_start": section_char_start,
            })

    # Merge entries shorter than MIN_CHUNK_CHARS with their next neighbor
    merged_entries: list[dict] = []
    i = 0
    while i < len(split_entries):
        entry = split_entries[i]
        text = "\n".join(entry["lines"]).strip()
        if len(text) < MIN_CHUNK_CHARS and i + 1 < len(split_entries):
            next_entry = split_entries[i + 1]
            merged_lines = entry["lines"] + next_entry["lines"]
            merged_entries.append({
                "lines": merged_lines,
                "timestamp": entry["timestamp"],  # keep earlier timestamp
                "char_start": entry["char_start"],
            })
            i += 2
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
                metadata={"archetype": "B"},
            )
        )

    # Fall back to single whole-note chunk if no boundaries detected
    if not chunks:
        chunks = [
            Chunk(
                chunk_index=0,
                chunk_text=body.strip(),
                char_start=0,
                char_end=len(body),
                metadata={"archetype": "B"},
            )
        ]

    return chunks