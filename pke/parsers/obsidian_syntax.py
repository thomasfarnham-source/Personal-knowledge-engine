"""
pke/parsers/obsidian_syntax.py

Strip Obsidian-specific inline markers that degrade embedding quality.

Why this exists:
- Obsidian wiki-link and callout syntax is authoring metadata, not semantic
  prose. Leaving markers like [[...]] or [!note] in text can produce false
  similarity matches during retrieval.
- We preserve the human-readable content while removing wrapper syntax so
  embeddings reflect intent and meaning, not editor-specific tokens.
- Fenced code blocks are intentionally preserved verbatim because stripping
  markers inside code can corrupt literal examples and alter meaning.
"""

import re

# ---------------------------------------------------------------------------
# 1. Fenced code block splitter
#
# Target: Triple-backtick fenced blocks.
# Example: "```\n[[x]]\n```" -> preserved unchanged.
#
# We split text into alternating [non-code, code, non-code, ...] segments.
# The stripper only runs on non-code segments, which avoids accidental edits
# to literal syntax examples inside code fences.
# ---------------------------------------------------------------------------
FENCED_CODE_BLOCK_RE = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)

# ---------------------------------------------------------------------------
# 2. Obsidian comment blocks
#
# Target: "%% ... %%" comments.
# Example: "a %%hidden%% b" -> "a  b"
# ---------------------------------------------------------------------------
COMMENT_RE = re.compile(r"%%[\s\S]*?%%")

# ---------------------------------------------------------------------------
# 3. Callout markers in blockquotes
#
# Target: Callout tag prefix only (keep blockquote content).
# Example: "> [!attention] Important" -> "> Important"
#
# NOTE: trailing whitespace class is [ \t]* (not \s*) so newline boundaries
# are preserved for multi-line callouts.
# ---------------------------------------------------------------------------
CALLOUT_RE = re.compile(r"(^\s*>\s*)\[\![^\]]+\][ \t]*", re.MULTILINE)

# ---------------------------------------------------------------------------
# 4. Wiki links with alias (anchor optional)
#
# Target: [[Note|Display]] and [[Note#Heading|Display]].
# Example: "[[Daily Drop|Today]]" -> "Today"
# Example: "[[Daily Drop#threat|Today]]" -> "Today"
# ---------------------------------------------------------------------------
WIKILINK_ALIAS_RE = re.compile(r"\[\[[^\]|]+(?:#[^\]|]+)?\|([^\]]+)\]\]")

# ---------------------------------------------------------------------------
# 5. Wiki links with anchor and no alias
#
# Target: [[Note#Heading]]
# Example: "[[Daily Drop#The threat]]" -> "Daily Drop The threat"
# ---------------------------------------------------------------------------
WIKILINK_ANCHOR_RE = re.compile(r"\[\[([^\]#|]+)#([^\]|]+)\]\]")

# ---------------------------------------------------------------------------
# 6. Wiki links without anchor or alias
#
# Target: [[Note Name]]
# Example: "[[Note Name]]" -> "Note Name"
# ---------------------------------------------------------------------------
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)\]\]")

# ---------------------------------------------------------------------------
# 7. Obsidian highlights
#
# Target: ==text==
# Example: "==Linkedin IDEA==" -> "Linkedin IDEA"
#
# KNOWN LIMIT: Chains like "==a==b==c==" are ambiguous and this regex may
# drop middle content. Known limit, see milestone 9.9 build log.
# ---------------------------------------------------------------------------
HIGHLIGHT_RE = re.compile(r"==(.+?)==")


# ---------------------------------------------------------------------------
# 8. Non-code segment stripper
#
# Substitution order is intentional for current milestone cases:
#   comments -> callouts -> alias links -> anchor links -> plain links -> highlight
#
# KNOWN LIMIT: Highly mixed link forms in one token (rare pathological
# combinations of alias + anchor-like content) may require reordered or
# tokenized parsing in a future milestone. Known limit, see milestone 9.9
# build log.
# ---------------------------------------------------------------------------
def _strip_obsidian_syntax_non_code(text: str) -> str:
    """Apply Obsidian syntax stripping to prose segments only."""
    text = COMMENT_RE.sub("", text)
    text = CALLOUT_RE.sub(r"\1", text)
    text = WIKILINK_ALIAS_RE.sub(r"\1", text)
    text = WIKILINK_ANCHOR_RE.sub(r"\1 \2", text)
    text = WIKILINK_RE.sub(r"\1", text)
    text = HIGHLIGHT_RE.sub(r"\1", text)
    return text


# ---------------------------------------------------------------------------
# 9. Public entry point
# ---------------------------------------------------------------------------
def strip_obsidian_syntax(text: str) -> str:
    """
    Strip Obsidian-specific markup while preserving fenced code blocks.

    Approach:
    1. Split on fenced blocks (capturing delimiters) so code blocks stay as-is.
    2. Run regex stripping only on non-code slices.
    3. Rejoin all slices in original order.
    """
    if not text:
        return text

    parts = FENCED_CODE_BLOCK_RE.split(text)

    for index, part in enumerate(parts):
        # Even indexes are non-code slices; odd indexes are fenced blocks.
        if index % 2 == 0:
            parts[index] = _strip_obsidian_syntax_non_code(part)

    return "".join(parts)
