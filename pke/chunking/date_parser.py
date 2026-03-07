"""
Date parsing utilities for the Personal Knowledge Engine chunker.

Personal notes use inconsistent, informal date formats. This module
normalizes them to ISO 8601 (YYYY-MM-DD) for storage in entry_timestamp.

Two public functions:

    parse_date(text, fallback_year) → "YYYY-MM-DD" | None
        Extracts and normalizes a date from any string.
        Used by archetype chunkers to set entry_timestamp on each chunk.

    is_date_header(line, prev_line) → bool
        Determines whether a line is a section demarcator (a date that
        marks the start of a new entry) vs. a date mentioned inline
        within prose.
        Used by archetype chunkers to find split points.

Design principles:
    - Never raise — return None gracefully when no date is found
    - Never guess silently — flag ambiguous M/D vs D/M interpretations
    - Two-digit years are always interpreted as 2000+ (19 → 2019)
    - Missing year is inferred from fallback_year when provided
    - is_date_header uses a 10-word length heuristic — headers are short
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

# ============================================================================
# CONSTANTS
# ============================================================================

# Month name → month number, handles full and abbreviated forms
MONTH_NAMES: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

# Day names to strip from lines before date parsing
DAY_NAMES = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "mon",
    "tue",
    "wed",
    "thu",
    "fri",
    "sat",
    "sun",
}

# Maximum word count for a line to be considered a section header
DATE_HEADER_MAX_WORDS = 10


# ============================================================================
# PUBLIC API
# ============================================================================


def parse_date(
    text: str,
    fallback_year: Optional[int] = None,
) -> Optional[str]:
    """
    Extract and normalize a date from a string to "YYYY-MM-DD".

    Strips leading day names (Monday, Tue, etc.) before parsing.
    Uses fallback_year when the text contains no year component.
    Two-digit years are interpreted as 2000+ (19 → 2019, 26 → 2026).

    Formats handled (in detection order):
        YYYYMMDD            — audio filename timestamps (e.g. 20150621)
        YYYY-MM-DD          — ISO format
        M/D/YYYY or M/D/YY  — American slash (e.g. 3/7/2026, 1/3/19)
        M/D                 — American slash, no year (uses fallback_year)
        M.D.YY or M-D-YY    — dot or dash separator
        Month D, YYYY       — month name, full (e.g. January 3, 2019)
        Month D             — month name, no year (uses fallback_year)

    Ambiguity:
        Dates where month and day are both ≤ 12 (e.g. 3/7/26) are
        ambiguous between M/D and D/M interpretations. The function
        defaults to M/D (American) and returns the result normally.
        Callers that need to detect ambiguity should call is_ambiguous_date().

    Arguments:
        text:          any string — sentence, header line, filename fragment
        fallback_year: year to use when text contains no year component,
                       typically extracted from the note's created_at field

    Returns:
        "YYYY-MM-DD" string, or None if no date is detectable
    """
    text = text.strip()

    # Strip leading day name if present (e.g. "Tuesday 9/8/15" → "9/8/15")
    text = _strip_day_name(text)

    # Try each format in order of specificity
    result = (
        _parse_yyyymmdd(text)
        or _parse_iso(text)
        or _parse_slash(text, fallback_year)
        or _parse_separated(text, fallback_year)
        or _parse_month_name(text, fallback_year)
    )

    return result


def is_date_header(
    line: str,
    prev_line: str = "",
) -> bool:
    """
    Return True if line is a section demarcator rather than inline content.

    A line is a date header when:
        1. It contains a recognizable date pattern
        2. The date appears at or near the start of the line
        3. It is short — fewer than DATE_HEADER_MAX_WORDS words
        4. The previous line is blank, a heading, or another date header
           (i.e. we are not mid-paragraph)

    Decoration that does not count toward word limit:
        Markdown heading markers (##, ###)
        Bold markers (**)
        Leading/trailing dashes or em-dashes

    Arguments:
        line:      the candidate line
        prev_line: the line immediately before (used to detect mid-paragraph)

    Returns:
        bool
    """
    stripped = _strip_decoration(line).strip()

    # Must contain a date pattern anywhere in the line
    if not parse_date(stripped):
        return False

    # Date must appear at or near the start — not embedded mid-sentence.
    # Strip pure punctuation tokens before checking so that separators
    # like " - " and " — " between day markers and dates don't push
    # the date beyond the lookahead window.
    words = [w for w in stripped.split() if w not in {"-", "—", "–"}]
    first_word = words[0] if words else ""
    if not parse_date(first_word) and not parse_date(" ".join(words[:4])):
        return False

    # Must be short enough to be a header
    word_count = len(stripped.split())
    if word_count >= DATE_HEADER_MAX_WORDS:
        return False

    # Must not be mid-paragraph — previous line must be blank or a header
    if prev_line.strip() and not _is_header_line(prev_line):
        return False

    return True


def is_ambiguous_date(text: str) -> bool:
    """
    Return True if the date in text could be read as either M/D or D/M.

    A date is ambiguous when both the first and second numeric components
    are ≤ 12, making it impossible to distinguish month from day without
    additional context (e.g. 3/7/26 could be March 7 or July 3).

    Arguments:
        text: a date string (should already be stripped to the date portion)

    Returns:
        bool
    """
    match = re.search(r"(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.]?", text)
    if not match:
        return False
    a, b = int(match.group(1)), int(match.group(2))
    return a <= 12 and b <= 12 and a != b


# ============================================================================
# PRIVATE HELPERS — FORMAT-SPECIFIC PARSERS
# ============================================================================


def _parse_yyyymmdd(text: str) -> Optional[str]:
    """
    Parse compact YYYYMMDD format used in audio filenames.
    Example: "20150621" → "2015-06-21"
    Only matches exactly 8 digits to avoid false positives.
    """
    match = re.search(r"\b(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b", text)
    if match:
        y, m, d = match.group(1), match.group(2), match.group(3)
        return _format_date(int(y), int(m), int(d))
    return None


def _parse_iso(text: str) -> Optional[str]:
    """
    Parse ISO 8601 date format.
    Example: "2019-03-15" → "2019-03-15"
    """
    match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return _format_date(y, m, d)
    return None


def _parse_slash(text: str, fallback_year: Optional[int]) -> Optional[str]:
    """
    Parse American slash-separated dates: M/D/YY, M/D/YYYY, or M/D.
    Examples:
        "3/7/2026"  → "2026-03-07"
        "1/3/19"    → "2019-01-03"
        "1/3"       → "FALLBACK_YEAR-01-03"
    Defaults to M/D interpretation (American) for ambiguous dates.
    """
    # With year
    match = re.search(r"\b(\d{1,2})\/(\d{1,2})\/(\d{2,4})\b", text)
    if match:
        m, d, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
        y = _normalize_year(y)
        return _format_date(y, m, d)

    # Without year — requires fallback_year
    match = re.search(r"\b(\d{1,2})\/(\d{1,2})\b", text)
    if match and fallback_year:
        m, d = int(match.group(1)), int(match.group(2))
        return _format_date(fallback_year, m, d)

    return None


def _parse_separated(text: str, fallback_year: Optional[int]) -> Optional[str]:
    """
    Parse dot or dash separated dates: M.D.YY or M-D-YY.
    Examples:
        "3.15.19"  → "2019-03-15"
        "3-15-19"  → "2019-03-15"
    Excludes ISO format (already handled by _parse_iso).
    """
    match = re.search(r"\b(\d{1,2})[.\-](\d{1,2})[.\-](\d{2,4})\b", text)
    if match:
        m, d, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
        # Exclude ISO-like YYYY-MM-DD (year would be 4 digits in first position)
        if len(match.group(1)) == 4:
            return None
        y = _normalize_year(y)
        return _format_date(y, m, d)
    return None


def _parse_month_name(text: str, fallback_year: Optional[int]) -> Optional[str]:
    """
    Parse dates with written month names.
    Examples:
        "January 3, 2019"  → "2019-01-03"
        "Jan 3, 2019"      → "2019-01-03"
        "March 15"         → "FALLBACK_YEAR-03-15"
    """
    pattern = re.search(
        r"\b([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?" r"(?:[,\s]+(\d{2,4}))?\b",
        text,
        re.IGNORECASE,
    )
    if not pattern:
        return None

    month_str = pattern.group(1).lower().rstrip(".")
    if month_str not in MONTH_NAMES:
        return None

    m = MONTH_NAMES[month_str]
    d = int(pattern.group(2))
    y_str = pattern.group(3)

    if y_str:
        y = _normalize_year(int(y_str))
    elif fallback_year:
        y = fallback_year
    else:
        return None

    return _format_date(y, m, d)


# ============================================================================
# PRIVATE HELPERS — UTILITIES
# ============================================================================


def _normalize_year(y: int) -> int:
    """
    Normalize two-digit years to four-digit years.
    All two-digit years are assumed to be 2000+.
    Example: 19 → 2019, 26 → 2026
    Four-digit years are returned unchanged.
    """
    if y < 100:
        return 2000 + y
    return y


def _format_date(year: int, month: int, day: int) -> Optional[str]:
    """
    Validate and format a date as "YYYY-MM-DD".
    Returns None if the date is invalid (e.g. month 13, day 32).
    """
    try:
        dt = datetime(year, month, day)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def _strip_day_name(text: str) -> str:
    """
    Remove a leading day name from a string.
    Example: "Tuesday 9/8/15" → "9/8/15"
    Example: "Monday, Jan 3" → "Jan 3"
    Only strips from the start of the string.
    """
    pattern = r"^(?:" + "|".join(DAY_NAMES) + r")\.?[,.\s]+"
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()


def _strip_decoration(line: str) -> str:
    """
    Remove markdown and formatting decoration from a line.
    Strips: ## heading markers, ** bold markers, leading dashes/em-dashes.
    Used by is_date_header to normalize before word counting.
    Examples:
        "## 2019-03-15"    → "2019-03-15"
        "**3/7/2026**"     → "3/7/2026"
        "— Tuesday 9/8/15" → "Tuesday 9/8/15"
    """
    line = re.sub(r"^#+\s*", "", line)
    line = re.sub(r"\*\*", "", line)
    line = re.sub(r"^[\-—–]\s*", "", line)
    return line.strip()


def _is_header_line(line: str) -> bool:
    """
    Return True if a line looks like a header or is blank.
    Used by is_date_header to validate the previous line context.
    A line is a header if it starts with ##, is blank, or is itself a date.
    """
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if parse_date(stripped):
        return True
    return False
