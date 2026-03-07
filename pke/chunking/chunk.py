"""
Chunk dataclass — the atomic unit of retrieval in the PKE chunking pipeline.

Imported by chunker.py and all archetype modules.
Defined here to avoid circular imports between chunker.py and archetype files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Chunk:
    """
    A single chunk of a note, ready to be written to the chunks table.

    Fields:
        chunk_index:     position in the note's chunk sequence (0-based)
        chunk_text:      cleaned text with all resource references stripped
        char_start:      start position in the original note body
        char_end:        end position in the original note body
        section_title:   nearest heading above this chunk, if any
        entry_timestamp: explicit date ("2015-09-08"), calculated date
                         ("calculated: 2014-08-04"), or None
        resource_ids:    resource IDs extracted from this chunk (images, audio)
        metadata:        archetype-specific flags e.g. note_type, resource_type
    """

    chunk_index: int
    chunk_text: str
    char_start: int
    char_end: int
    section_title: Optional[str] = None
    entry_timestamp: Optional[str] = None
    resource_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
