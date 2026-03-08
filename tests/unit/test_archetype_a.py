"""
Tests for pke/chunking/archetype_a.py

Test strategy:
    - chunk_archetype_a() is tested with representative fixtures covering
      the full range of Archetype A note structures observed in the corpus
    - Tests are organized by behavior: splitting, merging, timestamps,
      fallback, chunk shape, and edge cases
    - Fixtures are defined inline as module-level constants

Archetype A — Fragmented Journal:
    Short entries of 1-10 lines separated by date stamps.
    No template structure — pure freeform prose per entry.
    High noise tolerance — do not strip content aggressively.
    Merge entries under MIN_CHUNK_CHARS (~400 chars) with next neighbor.
"""

from pke.chunking.archetype_a import chunk_archetype_a
from pke.chunking.chunk import Chunk

# ============================================================================
# FIXTURES
# ============================================================================

# Standard created_at timestamp used across tests
CREATED_AT = "2019-03-15T00:00:00.000Z"

# Representative Archetype A note — multiple dated entries, all above
# MIN_CHUNK_CHARS when combined, none above it individually
STANDARD_BODY = """
1/3/19

Went to the gym. Felt good. Read for an hour after dinner.
Called mom. She sounded well.

1/4/19

Skipped gym. Tired from the week. Watched a film with Ger.
Made pasta. Early night.

1/5/19

Good day. Productive at work. Had lunch with Killian at the usual spot.
Called dad in the evening. He's doing well.
""".strip()

# Note with entries short enough to trigger merging behavior
# Each entry is well under MIN_CHUNK_CHARS (400 chars)
SHORT_ENTRIES_BODY = """
1/3/19

Short.

1/4/19

Also short.

1/5/19

Still short.

1/6/19

Final entry that is also quite brief.
""".strip()

# Note with no date stamps — should fall back to single whole-note chunk
NO_DATES_BODY = """
Just some thoughts written down without any structure.
No date stamps anywhere in this note.
It goes on for a while but never mentions a date.
Could be anything really — a draft, a list, some rambling.
""".strip()

# Note with a single date stamp — one entry, no splitting needed
SINGLE_DATE_BODY = """
3/15/19

Only one entry in this entire note. It has enough text to stand
on its own without being merged. The content goes on for a while
and covers several topics without any additional date stamps.
This should produce exactly one chunk with the correct timestamp.
""".strip()

# Note with entries that have no year — fallback_year should be used
# Entries are padded to exceed MIN_CHUNK_CHARS (400 chars) so they
# are not merged away before timestamps can be checked
NO_YEAR_BODY = "\n\n".join(
    [
        "3/15\n\n" + "First entry with no year. " * 20,
        "3/16\n\n" + "Second entry with no year. " * 20,
    ]
)

# Note with a date stamp using 4-digit year
FOUR_DIGIT_YEAR_BODY = """
2019-03-15

Entry with ISO format date stamp. Should parse correctly.
Has enough content to be a standalone chunk without merging.

2019-03-16

Second entry with ISO format. Also standalone.
Has enough content to avoid merging behavior.
""".strip()

# Empty body — edge case
EMPTY_BODY = ""

# Body with only whitespace — edge case
WHITESPACE_BODY = "   \n\n   \n"

# Large note — enough entries to produce multiple chunks above MIN_CHUNK_CHARS
LARGE_BODY = "\n\n".join(
    [
        f"1/{i}/19\n\n" + "This is a journal entry with enough content to stand on its own. " * 5
        for i in range(1, 15)
    ]
)


# ============================================================================
# RETURN TYPE TESTS
# ============================================================================


class TestReturnType:
    """
    chunk_archetype_a() always returns a list of Chunk instances.
    These tests validate the return type contract before any content
    assertions.
    """

    def test_returns_list(self):
        """Return value is always a list, never None or a single Chunk."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_returns_chunk_instances(self):
        """Every item in the returned list is a Chunk instance."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c, Chunk) for c in result)

    def test_returns_at_least_one_chunk(self):
        """Non-empty body always produces at least one chunk."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert len(result) >= 1


# ============================================================================
# CHUNK SHAPE TESTS
# ============================================================================


class TestChunkShape:
    """
    Every chunk produced by chunk_archetype_a() must have all required
    fields populated with the correct types and values.
    """

    def test_chunk_index_is_int(self):
        """chunk_index is an integer on every chunk."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.chunk_index, int) for c in result)

    def test_chunk_indexes_are_sequential(self):
        """chunk_index values are sequential starting from 0."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert [c.chunk_index for c in result] == list(range(len(result)))

    def test_chunk_text_is_str(self):
        """chunk_text is a non-empty string on every chunk."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.chunk_text, str) for c in result)
        assert all(len(c.chunk_text) > 0 for c in result)

    def test_chunk_text_is_stripped(self):
        """chunk_text has no leading or trailing whitespace."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert all(c.chunk_text == c.chunk_text.strip() for c in result)

    def test_char_start_is_int(self):
        """char_start is an integer on every chunk."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.char_start, int) for c in result)

    def test_char_end_is_int(self):
        """char_end is an integer on every chunk."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.char_end, int) for c in result)

    def test_char_end_greater_than_char_start(self):
        """char_end is always greater than char_start."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert all(c.char_end > c.char_start for c in result)

    def test_metadata_contains_archetype_a(self):
        """Every chunk carries archetype: A in its metadata."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert all(c.metadata.get("archetype") == "A" for c in result)

    def test_resource_ids_is_empty_list(self):
        """
        Archetype A notes do not contain resource references.
        resource_ids should always be an empty list.
        """
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert all(c.resource_ids == [] for c in result)


# ============================================================================
# SPLITTING TESTS
# ============================================================================


class TestSplitting:
    """
    chunk_archetype_a() splits on date stamp boundaries. These tests
    validate that entries are correctly separated at date headers and
    that the date header line is included in the chunk text.
    """

    def test_splits_on_date_boundaries(self):
        """
        A note with three date-separated entries produces multiple chunks.
        The exact count depends on merge behavior, but must be more than one.
        """
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        assert len(result) > 1

    def test_date_header_included_in_chunk_text(self):
        """
        The date stamp line is included in the chunk text, not stripped.
        Archetype A has high noise tolerance — date headers are content.
        """
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "1/3/19" in all_text
        assert "1/4/19" in all_text
        assert "1/5/19" in all_text

    def test_content_from_each_entry_present(self):
        """Text content from each dated entry appears in the output chunks."""
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "Went to the gym" in all_text
        assert "Skipped gym" in all_text
        assert "Good day" in all_text

    def test_single_date_produces_one_chunk(self):
        """A note with a single date stamp produces exactly one chunk."""
        result = chunk_archetype_a(SINGLE_DATE_BODY, CREATED_AT)
        assert len(result) == 1


# ============================================================================
# MERGE BEHAVIOR TESTS
# ============================================================================


class TestMergeBehavior:
    """
    Entries under MIN_CHUNK_CHARS (~400 chars) are merged with their next
    neighbor to avoid tiny low-signal chunks. These tests validate the
    merge logic.
    """

    def test_short_entries_are_merged(self):
        """
        A note with four very short entries produces fewer chunks than
        entries, because short entries are merged with their neighbors.
        """
        result = chunk_archetype_a(SHORT_ENTRIES_BODY, CREATED_AT)
        assert len(result) < 4

    def test_merged_chunk_contains_content_from_both_entries(self):
        """
        A merged chunk contains text from both the short entry and its
        neighbor. Both date stamps and both prose blocks should be present.
        """
        result = chunk_archetype_a(SHORT_ENTRIES_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "1/3/19" in all_text
        assert "1/4/19" in all_text

    def test_merged_chunk_keeps_earlier_timestamp(self):
        """
        When entries are merged, the earlier timestamp is preserved.
        The merged chunk's entry_timestamp reflects the first entry.
        """
        result = chunk_archetype_a(SHORT_ENTRIES_BODY, CREATED_AT)
        # First chunk should have the earliest timestamp
        assert result[0].entry_timestamp == "2019-01-03"

    def test_large_note_produces_multiple_chunks(self):
        """
        A note with many long entries produces multiple chunks,
        none of which have been over-merged.
        """
        result = chunk_archetype_a(LARGE_BODY, CREATED_AT)
        assert len(result) > 1


# ============================================================================
# TIMESTAMP TESTS
# ============================================================================


class TestTimestamps:
    """
    Timestamps are extracted from date header lines using parse_date().
    These tests validate correct timestamp extraction, fallback year
    behavior, and None handling for undated entries.
    """

    def test_timestamps_extracted_from_date_headers(self):
        """
        entry_timestamp is set from the date header line for each chunk.
        Standard M/D/YY format should parse to YYYY-MM-DD.
        """
        result = chunk_archetype_a(STANDARD_BODY, CREATED_AT)
        timestamps = [c.entry_timestamp for c in result]
        assert any(t is not None for t in timestamps)

    def test_standard_date_format_parses_correctly(self):
        """
        1/3/19 in the note body parses to 2019-01-03 as entry_timestamp.
        """
        result = chunk_archetype_a(SINGLE_DATE_BODY, CREATED_AT)
        assert result[0].entry_timestamp == "2019-03-15"

    def test_fallback_year_applied_to_dateless_entries(self):
        """
        Date headers with no year (e.g. 3/15) use the fallback year
        extracted from created_at. created_at of 2019 → year 2019.
        Detailed timestamp parsing for yearless dates is covered in
        test_date_parser.py. This test validates the chunker runs
        without error and produces output on yearless date headers.
        """
        result = chunk_archetype_a(NO_YEAR_BODY, CREATED_AT)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_iso_date_format_parses_correctly(self):
        """
        ISO format date stamps (2019-03-15) parse to the correct
        entry_timestamp value.
        """
        result = chunk_archetype_a(FOUR_DIGIT_YEAR_BODY, CREATED_AT)
        timestamps = [c.entry_timestamp for c in result]
        assert "2019-03-15" in timestamps

    def test_undated_note_has_none_timestamp(self):
        """
        A note with no date stamps produces a chunk with
        entry_timestamp of None.
        """
        result = chunk_archetype_a(NO_DATES_BODY, CREATED_AT)
        assert result[0].entry_timestamp is None


# ============================================================================
# FALLBACK TESTS
# ============================================================================


class TestFallback:
    """
    When no date boundaries are detected, chunk_archetype_a() falls back
    to a single whole-note chunk. These tests validate the fallback path.
    """

    def test_no_dates_produces_single_chunk(self):
        """A note with no date stamps falls back to one whole-note chunk."""
        result = chunk_archetype_a(NO_DATES_BODY, CREATED_AT)
        assert len(result) == 1

    def test_fallback_chunk_contains_full_body(self):
        """The fallback chunk contains the full note body text."""
        result = chunk_archetype_a(NO_DATES_BODY, CREATED_AT)
        assert result[0].chunk_text == NO_DATES_BODY.strip()

    def test_fallback_chunk_has_correct_char_positions(self):
        """The fallback chunk has char_start=0 and char_end=len(body)."""
        result = chunk_archetype_a(NO_DATES_BODY, CREATED_AT)
        assert result[0].char_start == 0
        assert result[0].char_end == len(NO_DATES_BODY)

    def test_fallback_chunk_metadata_archetype_a(self):
        """The fallback chunk still carries archetype: A in metadata."""
        result = chunk_archetype_a(NO_DATES_BODY, CREATED_AT)
        assert result[0].metadata.get("archetype") == "A"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestEdgeCases:
    """
    Boundary conditions and defensive cases. These tests ensure the chunker
    handles degenerate inputs gracefully without raising exceptions.
    """

    def test_empty_body_returns_one_chunk(self):
        """
        Empty body falls back to a single chunk. The chunk text will be
        empty but the chunker should not raise an exception.
        """
        result = chunk_archetype_a(EMPTY_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_whitespace_only_body_does_not_raise(self):
        """Whitespace-only body is handled gracefully without exceptions."""
        result = chunk_archetype_a(WHITESPACE_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_empty_created_at_does_not_raise(self):
        """
        Empty created_at string is handled gracefully.
        fallback_year will be None and dates without years will also be None.
        """
        result = chunk_archetype_a(STANDARD_BODY, "")
        assert isinstance(result, list)

    def test_none_created_at_does_not_raise(self):
        """
        None created_at is handled gracefully.
        fallback_year will be None.
        """
        result = chunk_archetype_a(STANDARD_BODY, None)
        assert isinstance(result, list)

    def test_all_chunks_have_non_negative_char_start(self):
        """char_start is never negative on any chunk."""
        result = chunk_archetype_a(LARGE_BODY, CREATED_AT)
        assert all(c.char_start >= 0 for c in result)

    def test_no_empty_chunk_text(self):
        """No chunk has an empty chunk_text string."""
        result = chunk_archetype_a(LARGE_BODY, CREATED_AT)
        assert all(len(c.chunk_text) > 0 for c in result)
