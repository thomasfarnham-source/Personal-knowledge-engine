"""
Resource extraction utilities for the Personal Knowledge Engine chunker.

Extracts embedded media resource IDs from note text and returns cleaned
text with all resource references stripped. Used by archetype chunkers
that handle notes with embedded images and audio recordings.

Formats handled:
    Markdown image:  ![alt](:/resource_id)          → type: image
    HTML image:      <img src=":/resource_id" .../>  → type: image
    Audio link:      [filename.m4a](:/resource_id)   → type: audio

Broken placeholders stripped silently — no resource_id stored:
    {picture)    (Picture)    (picture)    image

Called by:
    pke/chunking/archetype_d.py
    pke/chunking/archetype_e.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ============================================================================
# RESOURCE RESULT — RETURN TYPE
# ============================================================================

@dataclass
class ResourceResult:
    """
    Result of extracting resources from a text block.

    Fields:
        clean_text:     text with all resource references stripped and
                        excess blank lines collapsed
        resource_ids:   extracted resource IDs in order of appearance
        resource_types: mapping of resource_id → "image" or "audio"
    """
    clean_text: str
    resource_ids: list[str] = field(default_factory=list)
    resource_types: dict[str, str] = field(default_factory=dict)


# ============================================================================
# COMPILED PATTERNS
# ============================================================================

# Markdown image: ![alt text](:/resource_id)
_MARKDOWN_IMAGE_RE = re.compile(r"!\[.*?\]\(:/([a-f0-9]+)\)")

# HTML image: <img src=":/resource_id" ... />
_HTML_IMAGE_RE = re.compile(
    r'<img[^>]+src=":/([a-f0-9]+)"[^>]*/?>',
    re.IGNORECASE,
)

# Audio link: [filename.m4a](:/resource_id)
_AUDIO_LINK_RE = re.compile(
    r"\[.*?\.(m4a|mp3|wav)\]\(:/([a-f0-9]+)\)",
    re.IGNORECASE,
)

# Broken placeholders — strip silently, no resource_id stored
_BROKEN_PLACEHOLDER_RE = re.compile(
    r"\{picture\)|\(Picture\)|\(picture\)|(?<!\w)image(?!\w)",
    re.IGNORECASE,
)


# ============================================================================
# PUBLIC API
# ============================================================================

def extract_resources(text: str) -> ResourceResult:
    """
    Extract resource IDs from text and return cleaned text.

    Processes all resource formats in order:
        1. Markdown images
        2. HTML images
        3. Audio links
        4. Broken placeholders (stripped, no ID stored)

    Resource IDs are collected in order of appearance.
    All resource references are stripped from the returned clean_text.
    Consecutive blank lines left by stripping are collapsed to two.

    Arguments:
        text: raw note or chunk text containing resource references

    Returns:
        ResourceResult with clean_text, resource_ids, and resource_types
    """
    resource_ids: list[str] = []
    resource_types: dict[str, str] = {}

    # Extract and strip markdown images
    for match in _MARKDOWN_IMAGE_RE.finditer(text):
        rid = match.group(1)
        if rid not in resource_types:
            resource_ids.append(rid)
            resource_types[rid] = "image"
    text = _MARKDOWN_IMAGE_RE.sub("", text)

    # Extract and strip HTML images
    for match in _HTML_IMAGE_RE.finditer(text):
        rid = match.group(1)
        if rid not in resource_types:
            resource_ids.append(rid)
            resource_types[rid] = "image"
    text = _HTML_IMAGE_RE.sub("", text)

    # Extract and strip audio links
    for match in _AUDIO_LINK_RE.finditer(text):
        rid = match.group(2)  # group(1) is extension, group(2) is resource_id
        if rid not in resource_types:
            resource_ids.append(rid)
            resource_types[rid] = "audio"
    text = _AUDIO_LINK_RE.sub("", text)

    # Strip broken placeholders silently
    text = _BROKEN_PLACEHOLDER_RE.sub("", text)

    # Collapse 3+ consecutive blank lines down to 2
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return ResourceResult(
        clean_text=text,
        resource_ids=resource_ids,
        resource_types=resource_types,
    )
