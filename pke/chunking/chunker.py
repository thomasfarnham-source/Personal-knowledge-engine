"""
Archetype-aware note chunker for the Personal Knowledge Engine.

This module is the single entry point for all chunking logic. It detects
the note archetype and delegates to the appropriate archetype-specific
chunker module. The orchestrator calls chunk_note() for every note above
the character threshold and receives a list of Chunk objects ready to be
written to the chunks table.

Archetype detection is centralized here. Archetype-specific chunking
implementations live in separate files (archetype_a.py through archetype_e.py).
The Chunk dataclass is defined in chunk.py to avoid circular imports.

Archetype detection order (most specific first):
    E — audio resource links present
    D — day markers or travel image patterns present
    C — undated opening block + dated log structure
    B — structured template headers present
    A — fallback

Detection uses both text patterns (primary) and optional metadata hints
(title, notebook) as tiebreakers for ambiguous cases.
"""

from __future__ import annotations

import re

from pke.chunking.archetype_a import chunk_archetype_a
from pke.chunking.archetype_b import chunk_archetype_b
from pke.chunking.archetype_c import chunk_archetype_c
from pke.chunking.archetype_d import chunk_archetype_d
from pke.chunking.archetype_e import chunk_archetype_e
from pke.chunking.chunk import Chunk

# ============================================================================
# PUBLIC API
# ============================================================================


def chunk_note(
    body: str,
    created_at: str,
    title: str = "",
    notebook: str = "",
    threshold: int = 1000,
) -> list[Chunk]:
    """
    Chunk a single note body into a list of Chunk objects.

    Returns an empty list if len(body) < threshold — the note is short
    enough that its note-level embedding is sufficient for retrieval.

    Arguments:
        body:       the full note body text
        created_at: ISO timestamp string from the note record,
                    used for Archetype D calculated date offsets
        title:      note title, used as a detection hint
        notebook:   notebook name, used as a detection hint
        threshold:  minimum character count to trigger chunking (default 1000)

    Returns:
        list[Chunk] — empty if note is below threshold
    """
    if len(body) < threshold:
        return []

    archetype = detect_archetype(body, title=title, notebook=notebook)

    dispatch = {
        "A": chunk_archetype_a,
        "B": chunk_archetype_b,
        "C": chunk_archetype_c,
        "D": chunk_archetype_d,
        "E": chunk_archetype_e,
    }

    chunker_fn = dispatch[archetype]
    return chunker_fn(body, created_at)


def detect_archetype(
    body: str,
    title: str = "",
    notebook: str = "",
) -> str:
    """
    Detect the note archetype from body text and optional metadata hints.

    Detection order is most-specific first to avoid false positives:
        E — audio resource links (.m4a, .mp3) present
        D — day markers or travel patterns present, or title/notebook hint
        C — undated opening block followed by dated log entries
        B — structured template section headers present
        A — fallback for date-stamp-only or unstructured notes

    Arguments:
        body:     full note body text
        title:    note title hint (optional)
        notebook: notebook name hint (optional)

    Returns:
        str — one of "A", "B", "C", "D", "E"
    """
    # --- Archetype E: audio recordings present ---
    if re.search(r"\[.*?\.(m4a|mp3|wav)\]\(:/", body, re.IGNORECASE):
        return "E"

    # --- Archetype D: travel patterns or metadata hint ---
    travel_title_hint = any(
        word in title.lower() for word in ["ireland", "travel", "trip", "vacation", "holiday"]
    )
    travel_notebook_hint = any(word in notebook.lower() for word in ["travel", "trips", "vacation"])
    day_marker_pattern = re.search(
        r"(?:^|\n)\s*(?:Day\s+\d+|Monday|Tuesday|Wednesday|Thursday"
        r"|Friday|Saturday|Sunday|Sat|Sun|Mon|Tue|Wed|Thu|Fri)",
        body,
        re.IGNORECASE,
    )
    if travel_title_hint or travel_notebook_hint or day_marker_pattern:
        return "D"

    # --- Archetype C: undated header + dated log ---
    has_dated_entries = re.search(
        r"(?:^|\n)#{1,3}\s*\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}",
        body,
    )
    has_undated_header = not re.match(
        r"^\s*#{1,3}\s*\d{1,2}[\/\-.]\d{1,2}",
        body.strip(),
    )
    if has_dated_entries and has_undated_header:
        return "C"

    # --- Archetype B: structured template headers ---
    template_headers = re.search(
        r"(?:^|\n)#{1,3}\s*(?:Score|What did I do well|Improvements"
        r"|Gratitude|Intentions|Goals|Summary|Notes)",
        body,
        re.IGNORECASE,
    )
    if template_headers:
        return "B"

    # --- Archetype A: fallback ---
    return "A"
