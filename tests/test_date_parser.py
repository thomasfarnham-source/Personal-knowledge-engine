"""
Tests for pke/chunking/date_parser.py

Test strategy:
    - parse_date() is tested against every format in the spec,
      including edge cases: missing year, two-digit year, day name prefix,
      invalid dates, and ambiguous M/D vs D/M inputs
    - is_date_header() is tested against real corpus examples —
      both positive cases (true headers) and negative cases (inline dates)
    - is_ambiguous_date() is tested for correct ambiguity detection
    - All private helpers are exercised indirectly through the public API

Fixtures are defined inline as module-level constants.
"""

from pke.chunking.date_parser import (
    is_ambiguous_date,
    is_date_header,
    parse_date,
)

FALLBACK_YEAR = 2021


# ============================================================================
# parse_date() — YYYYMMDD FORMAT
# ============================================================================


class TestParseDateYYYYMMDD:
    """
    Audio filename timestamps in compact YYYYMMDD format.
    This is the most reliable timestamp source in the corpus.
    """

    def test_basic_yyyymmdd(self):
        """Standard compact date from audio filename."""
        assert parse_date("Evernote 20150621 00:15:50.m4a") == "2015-06-21"

    def test_yyyymmdd_standalone(self):
        """Bare 8-digit date string."""
        assert parse_date("20190315") == "2019-03-15"

    def test_yyyymmdd_does_not_match_7_digits(self):
        """7-digit number should not be parsed as YYYYMMDD."""
        assert parse_date("2015062") is None

    def test_yyyymmdd_does_not_match_9_digits(self):
        """9-digit number should not be parsed as YYYYMMDD."""
        assert parse_date("201506210") is None


# ============================================================================
# parse_date() — ISO FORMAT
# ============================================================================


class TestParseDateISO:
    """ISO 8601 dates: YYYY-MM-DD."""

    def test_basic_iso(self):
        assert parse_date("2019-03-15") == "2019-03-15"

    def test_iso_in_header(self):
        """ISO date embedded in a markdown header."""
        assert parse_date("## 2019-03-15") == "2019-03-15"

    def test_iso_in_prose(self):
        """ISO date embedded in a sentence."""
        assert parse_date("On 2019-03-15 I went to the gym.") == "2019-03-15"

    def test_iso_invalid_month(self):
        """Month 13 should return None."""
        assert parse_date("2019-13-15") is None

    def test_iso_invalid_day(self):
        """Day 32 should return None."""
        assert parse_date("2019-03-32") is None


# ============================================================================
# parse_date() — AMERICAN SLASH FORMAT
# ============================================================================


class TestParseDateSlash:
    """
    American slash-separated dates: M/D/YY, M/D/YYYY, M/D.
    Most common format in the corpus for informal journal entries.
    """

    def test_slash_with_four_digit_year(self):
        assert parse_date("3/7/2026") == "2026-03-07"

    def test_slash_with_two_digit_year(self):
        """Two-digit year normalized to 2000+."""
        assert parse_date("1/3/19") == "2019-01-03"

    def test_slash_with_two_digit_year_26(self):
        assert parse_date("1/15/26") == "2026-01-15"

    def test_slash_no_year_with_fallback(self):
        """Missing year inferred from fallback_year."""
        assert parse_date("1/3", fallback_year=FALLBACK_YEAR) == "2021-01-03"

    def test_slash_no_year_without_fallback(self):
        """Missing year with no fallback returns None."""
        assert parse_date("1/3") is None

    def test_slash_invalid_month(self):
        """Month 13 should return None."""
        assert parse_date("13/7/2026") is None

    def test_slash_invalid_day(self):
        """Day 32 should return None."""
        assert parse_date("3/32/2026") is None

    def test_slash_in_prose(self):
        """Slash date embedded in a sentence."""
        assert parse_date("on 3/7/2026 I went to the store") == "2026-03-07"


# ============================================================================
# parse_date() — SEPARATED FORMAT (dot and dash)
# ============================================================================


class TestParseDateSeparated:
    """Dot and dash separated dates: M.D.YY, M-D-YY."""

    def test_dot_separator(self):
        assert parse_date("3.15.19") == "2019-03-15"

    def test_dash_separator(self):
        assert parse_date("3-15-19") == "2019-03-15"

    def test_dot_four_digit_year(self):
        assert parse_date("3.15.2019") == "2019-03-15"


# ============================================================================
# parse_date() — MONTH NAME FORMAT
# ============================================================================


class TestParseDateMonthName:
    """Written month name dates: January 3, 2019 / Jan 3 / March 15."""

    def test_full_month_name_with_year(self):
        assert parse_date("January 3, 2019") == "2019-01-03"

    def test_abbreviated_month_with_year(self):
        assert parse_date("Jan 3, 2019") == "2019-01-03"

    def test_abbreviated_month_with_period(self):
        """Abbreviated month with trailing period: Jan. 3, 2019"""
        assert parse_date("Jan. 3, 2019") == "2019-01-03"

    def test_month_name_no_year_with_fallback(self):
        assert parse_date("March 15", fallback_year=FALLBACK_YEAR) == "2021-03-15"

    def test_month_name_no_year_without_fallback(self):
        assert parse_date("March 15") is None

    def test_month_name_with_ordinal(self):
        """Ordinal suffixes like 3rd, 15th should be handled."""
        assert parse_date("January 3rd, 2019") == "2019-01-03"

    def test_month_name_case_insensitive(self):
        assert parse_date("MARCH 15, 2019") == "2019-03-15"

    def test_non_month_word_returns_none(self):
        """A word that looks like a month name but isn't should return None."""
        assert parse_date("Score 15, 2019") is None


# ============================================================================
# parse_date() — DAY NAME STRIPPING
# ============================================================================


class TestParseDateDayNameStripping:
    """
    Day names prefixing dates should be stripped before parsing.
    Common in corpus: "Tuesday 9/8/15", "Monday, Jan 3"
    Day names may appear with trailing punctuation: "Tue.", "Wed."
    """

    def test_full_day_name_prefix(self):
        assert parse_date("Tuesday 9/8/15") == "2015-09-08"

    def test_abbreviated_day_name_prefix(self):
        assert parse_date("Tue 9/8/15") == "2015-09-08"

    def test_abbreviated_day_name_with_period(self):
        """Abbreviated day name with trailing period."""
        assert parse_date("Tue. 9/8/15") == "2015-09-08"

    def test_day_name_with_comma(self):
        assert parse_date("Monday, Jan 3, 2019") == "2019-01-03"

    def test_day_name_with_period_and_month_with_period(self):
        """Both day and month abbreviated with periods."""
        assert parse_date("Tue., Jan. 3, 2019") == "2019-01-03"

    def test_day_name_case_insensitive(self):
        assert parse_date("TUESDAY 9/8/15") == "2015-09-08"


# ============================================================================
# parse_date() — FALLBACK YEAR INFERENCE
# ============================================================================


class TestParseDateFallbackYear:
    """
    When a date has no year component, fallback_year is used.
    fallback_year is typically extracted from the note's created_at field.
    """

    def test_slash_date_uses_fallback_year(self):
        assert parse_date("3/7", fallback_year=2019) == "2019-03-07"

    def test_month_name_uses_fallback_year(self):
        assert parse_date("March 7", fallback_year=2019) == "2019-03-07"

    def test_no_fallback_returns_none_for_incomplete_date(self):
        assert parse_date("3/7") is None

    def test_fallback_year_not_used_when_year_present(self):
        """Explicit year in text takes precedence over fallback_year."""
        assert parse_date("3/7/2026", fallback_year=2019) == "2026-03-07"


# ============================================================================
# parse_date() — EDGE CASES
# ============================================================================


class TestParseDateEdgeCases:
    """Edge cases and inputs that should return None gracefully."""

    def test_empty_string(self):
        assert parse_date("") is None

    def test_no_date_in_text(self):
        assert parse_date("Went to the gym today") is None

    def test_just_a_number(self):
        assert parse_date("42") is None

    def test_returns_none_not_raises(self):
        """Parser must never raise — garbage input returns None."""
        assert parse_date("!!!###@@@") is None


# ============================================================================
# is_date_header() — POSITIVE CASES
# ============================================================================


class TestIsDateHeaderPositive:
    """
    Lines that should be detected as section demarcators.
    Drawn from real corpus patterns.
    """

    def test_bare_slash_date(self):
        """Bare date on its own line — most common in Archetype A."""
        assert is_date_header("1/3/19") is True

    def test_markdown_heading_iso(self):
        """ISO date as markdown heading — common in Archetype B and C."""
        assert is_date_header("## 2019-03-15") is True

    def test_bold_date(self):
        """Bold date on its own line."""
        assert is_date_header("**3/7/2026**") is True

    def test_day_marker_with_date(self):
        """Day marker combined with date — Archetype D."""
        assert is_date_header("Day 1 - 3/7/2026") is True

    def test_day_name_with_date(self):
        """Day name and date as header — common in corpus."""
        assert is_date_header("Tuesday 9/8/15") is True

    def test_abbreviated_day_with_period_and_date(self):
        """Abbreviated day name with period followed by date."""
        assert is_date_header("Tue. 9/8/15") is True

    def test_date_with_location(self):
        """Short header combining date and location."""
        assert is_date_header("Tuesday 9/8/15 — Sligo") is True

    def test_preceded_by_blank_line(self):
        """Date header preceded by blank line."""
        assert is_date_header("1/3/19", prev_line="") is True

    def test_preceded_by_another_header(self):
        """Date header preceded by another short header."""
        assert is_date_header("1/4/19", prev_line="1/3/19") is True


# ============================================================================
# is_date_header() — NEGATIVE CASES
# ============================================================================


class TestIsDateHeaderNegative:
    """
    Lines that contain dates but should NOT be detected as section demarcators.
    """

    def test_date_mid_sentence(self):
        """Date appears mid-sentence — inline content."""
        assert is_date_header("on 3/7/2026 I went to the store and bought milk") is False

    def test_date_follows_prose(self):
        """Date follows prose on the same line."""
        assert is_date_header("Met John and discussed the project on 3/7/2026") is False

    def test_date_in_list_item(self):
        """Date embedded in a list item with surrounding text."""
        assert is_date_header("- Appointment scheduled for 3/7 with Dr. Smith") is False

    def test_long_line_with_date(self):
        """Line is too long to be a header even if it starts with a date."""
        assert (
            is_date_header("3/7/2026 was a really great day because the weather was perfect")
            is False
        )

    def test_date_preceded_by_prose_line(self):
        """Date on its own line but preceded by a prose line — mid-paragraph."""
        assert (
            is_date_header(
                "1/3/19",
                prev_line="This is a long sentence continuing a paragraph about something.",
            )
            is False
        )


# ============================================================================
# is_ambiguous_date()
# ============================================================================


class TestIsAmbiguousDate:
    """
    Dates where M/D vs D/M interpretation is ambiguous.
    Both components must be ≤ 12 for ambiguity to exist.
    """

    def test_ambiguous_both_under_12(self):
        """3/7 could be March 7 or July 3."""
        assert is_ambiguous_date("3/7/26") is True

    def test_not_ambiguous_day_over_12(self):
        """Day 15 cannot be a month — unambiguous."""
        assert is_ambiguous_date("3/15/19") is False

    def test_not_ambiguous_month_over_12(self):
        """First component 13 cannot be a month — unambiguous."""
        assert is_ambiguous_date("13/7/26") is False

    def test_not_ambiguous_same_values(self):
        """When both components are equal, ambiguity is moot."""
        assert is_ambiguous_date("7/7/26") is False

    def test_no_date_returns_false(self):
        """No date pattern — returns False not raises."""
        assert is_ambiguous_date("no date here") is False
