"""
Archetype C chunker — Reference / Medical Log.

Called by chunk_note() in chunker.py when detect_archetype() returns "C".

Structure:
    Undated opening block describing current state (most retrieval-valuable).
    Followed by dated log entries appended over time.
    Embedded sub-tables (e.g. injection schedules) interspersed in log.

Chunking strategy:
    1. Detect the undated opening block — all lines before the first
       date stamp header
    2. Emit the opening block as its own reference chunk (chunk_index 0)
    3. Split the remainder on date stamp boundaries using is_date_header()
    4. Keep embedded sub-tables intact — do not split on dates found
       inside markdown tables (lines starting with |)
    5. Merge any entry under MIN_CHUNK_CHARS with its next neighbor

Timestamps:
    - Opening block: entry_timestamp is None
    - Log entries: extracted from date header using parse_date()
    - Pass fallback_year extracted from created_at

Chunk text:
    - Include the date header line in each log chunk
    - Strip leading/trailing blank lines from each chunk

Metadata:
    - archetype: "C"
    - opening block gets reference: True flag
"""

from __future__ import annotations

from typing import Optional

from pke.chunking.chunk import Chunk
from pke.chunking.date_parser import is_date_header, parse_date

MIN_CHUNK_CHARS = 400  # ~100 tokens — merge entries shorter than this


def chunk_archetype_c(body: str, created_at: str) -> list[Chunk]:
    """
    Emit undated opening block as reference chunk, then split dated
    log entries on date stamp boundaries. Sub-tables kept intact.
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
    raw_entries: list[dict] = []

    current_lines: list[str] = []
    current_timestamp: Optional[str] = None
    current_char_start: int = 0
    char_pos: int = 0
    found_first_date: bool = False

    for i, line in enumerate(lines):
        prev_line = lines[i - 1] if i > 0 else ""

        # Do not split on dates inside markdown table rows
        is_table_row = line.strip().startswith("|")

        if not is_table_row and is_date_header(line, prev_line=prev_line):
            # Finalize previous block
            if current_lines:
                raw_entries.append(
                    {
                        "lines": current_lines,
                        "timestamp": current_timestamp,
                        "char_start": current_char_start,
                        "is_reference": not found_first_date,
                    }
                )
            found_first_date = True
            current_lines = [line]
            current_timestamp = parse_date(line, fallback_year=fallback_year)
            current_char_start = char_pos
        else:
            current_lines.append(line)

        char_pos += len(line) + 1

    # Finalize last entry
    if current_lines:
        raw_entries.append(
            {
                "lines": current_lines,
                "timestamp": current_timestamp,
                "char_start": current_char_start,
                "is_reference": not found_first_date,
            }
        )

    # Merge entries shorter than MIN_CHUNK_CHARS with their next neighbor
    # Never merge the reference block with a log entry
    merged_entries: list[dict] = []
    i = 0
    while i < len(raw_entries):
        entry = raw_entries[i]
        text = "\n".join(entry["lines"]).strip()
        next_exists = i + 1 < len(raw_entries)
        next_is_not_reference = next_exists and not raw_entries[i + 1]["is_reference"]
        if (
            len(text) < MIN_CHUNK_CHARS
            and not entry["is_reference"]
            and next_exists
            and next_is_not_reference
        ):
            next_entry = raw_entries[i + 1]
            merged_lines = entry["lines"] + next_entry["lines"]
            merged_entries.append(
                {
                    "lines": merged_lines,
                    "timestamp": entry["timestamp"],
                    "char_start": entry["char_start"],
                    "is_reference": False,
                }
            )
            i += 2
        else:
            merged_entries.append(entry)
            i += 1

    # Build Chunk objects
    chunks: list[Chunk] = []
    for idx, entry in enumerate(merged_entries):
        text = "\n".join(entry["lines"]).strip()
        if not text:
            continue
        char_start = entry["char_start"]
        char_end = char_start + len("\n".join(entry["lines"]))
        metadata: dict = {"archetype": "C"}
        if entry["is_reference"]:
            metadata["reference"] = True
        chunks.append(
            Chunk(
                chunk_index=idx,
                chunk_text=text,
                char_start=char_start,
                char_end=char_end,
                entry_timestamp=entry["timestamp"],
                metadata=metadata,
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
                metadata={"archetype": "C"},
            )
        ]

    return chunks
