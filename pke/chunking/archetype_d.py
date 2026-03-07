"""
Archetype D chunker — Travel Journal.

Called by chunk_note() in chunker.py when detect_archetype() returns "D".

Structure:
    Single note per multi-day trip, written in real time.
    Day markers in multiple formats interspersed throughout.
    Images and audio resources inline.
    Broken image placeholders present — strip silently.

Chunking strategy:
    1. Split on day marker boundaries using _is_day_marker()
    2. Pre-trip planning block (before first day marker) emitted
       as its own reference chunk
    3. Timestamp strategy (three tiers):
        Tier 1 — explicit date in chunk text → entry_timestamp directly
        Tier 2 — Day N or day name marker → "calculated: YYYY-MM-DD"
                 from created_at + day offset
        Tier 3 — no marker detectable → entry_timestamp null
    4. Resource IDs extracted from image and audio links
    5. Resource references and broken placeholders stripped from chunk text
    6. Merge chunks under MIN_CHUNK_CHARS with next neighbor

Day marker formats handled:
    Day 1, Day 2, Day 2 Harry Goldens Trail   (explicit numbered)
    Sunday, Monday, Saturday                   (standalone day names)
    Day name followed by content               (day name as header)

Resource formats handled:
    Markdown:  ![alt](:/resource_id)
    HTML:      <img src=":/resource_id" .../>
    Audio:     [filename.m4a](:/resource_id)

Broken placeholder formats stripped silently:
    {picture)    (Picture)    (picture)    image

Metadata:
    - archetype: "D"
    - note_type: "travel"
    - reference: True for pre-trip planning block
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from pke.chunking.chunk import Chunk
from pke.chunking.date_parser import parse_date

MIN_CHUNK_CHARS = 400  # ~100 tokens — merge chunks shorter than this

# Day marker pattern — matches Day N, Day N Title, or standalone day names
DAY_MARKER_RE = re.compile(
    r"^(?:Day\s+\d+|Monday|Tuesday|Wednesday|Thursday"
    r"|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b",
    re.IGNORECASE,
)

# Resource extraction patterns
MARKDOWN_IMAGE_RE = re.compile(r"!\[.*?\]\(:/([a-f0-9]+)\)")
HTML_IMAGE_RE = re.compile(r'<img[^>]+src=":/([a-f0-9]+)"[^>]*/?>',re.IGNORECASE)
AUDIO_LINK_RE = re.compile(r"\[.*?\.(m4a|mp3|wav)\]\(:/([a-f0-9]+)\)",re.IGNORECASE)

# Broken placeholder patterns — strip silently
BROKEN_PLACEHOLDER_RE = re.compile(
    r"\{picture\)|\(Picture\)|\(picture\)|(?<!\w)image(?!\w)",
    re.IGNORECASE,
)


def chunk_archetype_d(body: str, created_at: str) -> list[Chunk]:
    """
    Split on day marker boundaries. Extract resource IDs. Strip resource
    references and broken placeholders from chunk text. Apply three-tier
    timestamp strategy. Falls back to single whole-note chunk if no
    day markers detected.

    Arguments:
        body:       full note body text
        created_at: ISO timestamp string from the note record,
                    used for calculated date offsets from day markers

    Returns:
        list[Chunk]
    """
    # Extract created_at date for calculated timestamp offsets
    created_date: Optional[datetime] = None
    if created_at:
        try:
            created_date = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            created_date = None

    # Extract fallback year from created_at
    fallback_year: Optional[int] = None
    if created_date:
        fallback_year = created_date.year

    lines = body.splitlines()
    raw_entries: list[dict] = []

    current_lines: list[str] = []
    current_char_start: int = 0
    current_day_offset: Optional[int] = None
    char_pos: int = 0
    day_counter: int = 0
    found_first_marker: bool = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if DAY_MARKER_RE.match(stripped):
            # Finalize previous entry
            if current_lines:
                raw_entries.append({
                    "lines": current_lines,
                    "char_start": current_char_start,
                    "day_offset": current_day_offset,
                    "is_reference": not found_first_marker,
                })
            found_first_marker = True
            current_lines = [line]
            current_char_start = char_pos
            current_day_offset = day_counter
            day_counter += 1
        else:
            current_lines.append(line)

        char_pos += len(line) + 1

    # Finalize last entry
    if current_lines:
        raw_entries.append({
            "lines": current_lines,
            "char_start": current_char_start,
            "day_offset": current_day_offset,
            "is_reference": not found_first_marker,
        })

    # Merge entries shorter than MIN_CHUNK_CHARS with next neighbor
    merged_entries: list[dict] = []
    i = 0
    while i < len(raw_entries):
        entry = raw_entries[i]
        text = "\n".join(entry["lines"]).strip()
        next_exists = i + 1 < len(raw_entries)
        if (
            len(text) < MIN_CHUNK_CHARS
            and not entry["is_reference"]
            and next_exists
            and not raw_entries[i + 1]["is_reference"]
        ):
            next_entry = raw_entries[i + 1]
            merged_entries.append({
                "lines": entry["lines"] + next_entry["lines"],
                "char_start": entry["char_start"],
                "day_offset": entry["day_offset"],
                "is_reference": False,
            })
            i += 2
        else:
            merged_entries.append(entry)
            i += 1

    # Build Chunk objects
    chunks: list[Chunk] = []
    for idx, entry in enumerate(merged_entries):
        raw_text = "\n".join(entry["lines"])

        # Extract resource IDs
        resource_ids: list[str] = []
        resource_ids += MARKDOWN_IMAGE_RE.findall(raw_text)
        resource_ids += HTML_IMAGE_RE.findall(raw_text)
        audio_matches = AUDIO_LINK_RE.findall(raw_text)
        resource_ids += [match[1] for match in audio_matches]

        # Strip resource references from chunk text
        clean_text = MARKDOWN_IMAGE_RE.sub("", raw_text)
        clean_text = HTML_IMAGE_RE.sub("", clean_text)
        clean_text = AUDIO_LINK_RE.sub("", clean_text)

        # Strip broken placeholders
        clean_text = BROKEN_PLACEHOLDER_RE.sub("", clean_text)

        # Collapse multiple blank lines left by stripping
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()

        if not clean_text:
            continue

        # Determine entry_timestamp (three tiers)
        entry_timestamp: Optional[str] = None

        # Tier 1 — explicit date in chunk text
        explicit_date = parse_date(clean_text, fallback_year=fallback_year)
        if explicit_date:
            entry_timestamp = explicit_date

        # Tier 2 — calculated from created_at + day offset
        elif created_date is not None and entry["day_offset"] is not None:
            calculated = created_date + timedelta(days=entry["day_offset"])
            entry_timestamp = f"calculated: {calculated.strftime('%Y-%m-%d')}"

        # Tier 3 — no timestamp available
        # entry_timestamp remains None

        char_start = entry["char_start"]
        char_end = char_start + len(raw_text)

        metadata: dict = {"archetype": "D", "note_type": "travel"}
        if entry["is_reference"]:
            metadata["reference"] = True

        chunks.append(
            Chunk(
                chunk_index=idx,
                chunk_text=clean_text,
                char_start=char_start,
                char_end=char_end,
                entry_timestamp=entry_timestamp,
                resource_ids=resource_ids,
                metadata=metadata,
            )
        )

    # Fall back to single whole-note chunk if no day markers detected
    if not chunks:
        chunks = [
            Chunk(
                chunk_index=0,
                chunk_text=body.strip(),
                char_start=0,
                char_end=len(body),
                metadata={"archetype": "D", "note_type": "travel"},
            )
        ]

    return chunks