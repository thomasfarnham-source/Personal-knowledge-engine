"""
Tests for pke/chunking/archetype_c.py

Test strategy:
    - chunk_archetype_c() is tested with representative fixtures covering
      the full range of Archetype C note structures observed in the corpus
    - Tests are organized by behavior: reference chunk emission, dated log
      splitting, sub-table preservation, merging, timestamps, fallback,
      and chunk shape
    - Fixtures are defined inline as module-level constants

Archetype C — Reference / Medical Log:
    Undated opening block describing current state.
    Followed by dated log entries appended over time.
    Embedded sub-tables kept intact — not split on internal dates.
    Opening block emitted as its own reference chunk.
    Merge log entries under MIN_CHUNK_CHARS (~400 chars) with next neighbor.
"""

from pke.chunking.archetype_c import chunk_archetype_c
from pke.chunking.chunk import Chunk

# ============================================================================
# FIXTURES
# ============================================================================

# Standard created_at timestamp used across tests
CREATED_AT = "2026-01-15T00:00:00.000Z"

# Representative Archetype C note — undated opening block + dated log entries
# Each log entry is long enough to survive merging
STANDARD_BODY = """
## Current State
Currently on Taltz injection every 8 weeks. Managing well.
Last blood work normal. Next appointment March 2026.
No current flare-ups. Skin mostly clear. Energy levels good.
Following up with Dr. Smith next month for routine review.

---

## Log

### 1/15/26
Injection day. No side effects. Felt well throughout the day.
Energy was good. Skin remained clear. No joint pain reported.
Followed up with pharmacy to confirm next delivery schedule.

### 11/20/25
Mild fatigue for two days post-injection. Resolved by day three.
Skin showed minor irritation at injection site, cleared within 48hrs.
Blood work results came back normal across all markers reviewed.
""".strip()

# Note with only an opening block and no dated log entries
REFERENCE_ONLY_BODY = """
## Current State
Currently on Taltz injection every 8 weeks. Managing well.
Last blood work normal. Next appointment March 2026.
No current flare-ups. Skin mostly clear. Energy levels good.
Following up with Dr. Smith next month for routine review.
""".strip()

# Note with a sub-table embedded in the log — table must not be split
SUBTABLE_BODY = """
## Current State
Currently managing with weekly injections. Stable overall.
Next review scheduled for April 2026. Blood work pending.

## Log

### 3/1/26
Starting new injection schedule. See table below.

| Date     | Dose | Site      | Notes        |
|----------|------|-----------|--------------|
| 3/1/26   | 80mg | Left arm  | No reaction  |
| 3/8/26   | 80mg | Right arm | Minor redness|
| 3/15/26  | 80mg | Left arm  | Clear        |

Feeling well overall. No major side effects noted this cycle.

### 2/1/26
Previous cycle completed without issues. All markers normal.
Energy levels consistent. Skin clear throughout the period.
No changes to current treatment plan recommended by doctor.
""".strip()

# Note with short log entries that should be merged
SHORT_LOG_BODY = """
## Current State
Stable. Managing well on current treatment. No changes planned.
Energy good, skin clear, next appointment in three months time.

## Log

### 3/1/26
Short entry.

### 2/1/26
Also brief.

### 1/1/26
Another short one.

### 12/1/25
Final short entry.
""".strip()

# Note with no date stamps — falls back to single whole-note chunk
NO_DATES_BODY = """
## Current State
Stable on current medication. No recent changes to treatment.
Energy levels good. Next appointment scheduled for April 2026.

## Notes
General observations about current condition and treatment plan.
No specific dated entries recorded yet for this condition log.
""".strip()

# Empty body — edge case
EMPTY_BODY = ""


# ============================================================================
# RETURN TYPE TESTS
# ============================================================================


class TestReturnType:
    """
    chunk_archetype_c() always returns a list of Chunk instances.
    These tests validate the return type contract before any content
    assertions.
    """

    def test_returns_list(self):
        """Return value is always a list, never None or a single Chunk."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_returns_chunk_instances(self):
        """Every item in the returned list is a Chunk instance."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c, Chunk) for c in result)

    def test_returns_at_least_one_chunk(self):
        """Non-empty body always produces at least one chunk."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert len(result) >= 1


# ============================================================================
# CHUNK SHAPE TESTS
# ============================================================================


class TestChunkShape:
    """
    Every chunk produced by chunk_archetype_c() must have all required
    fields populated with the correct types and values.
    """

    def test_chunk_indexes_are_sequential(self):
        """chunk_index values are sequential starting from 0."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert [c.chunk_index for c in result] == list(range(len(result)))

    def test_chunk_text_is_non_empty_str(self):
        """chunk_text is a non-empty string on every chunk."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.chunk_text, str) for c in result)
        assert all(len(c.chunk_text) > 0 for c in result)

    def test_chunk_text_is_stripped(self):
        """chunk_text has no leading or trailing whitespace."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert all(c.chunk_text == c.chunk_text.strip() for c in result)

    def test_char_end_greater_than_char_start(self):
        """char_end is always greater than char_start."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert all(c.char_end > c.char_start for c in result)

    def test_metadata_contains_archetype_c(self):
        """Every chunk carries archetype: C in its metadata."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert all(c.metadata.get("archetype") == "C" for c in result)

    def test_resource_ids_is_empty_list(self):
        """
        Archetype C notes do not contain resource references.
        resource_ids should always be an empty list.
        """
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert all(c.resource_ids == [] for c in result)


# ============================================================================
# REFERENCE CHUNK TESTS
# ============================================================================


class TestReferenceChunk:
    """
    The undated opening block is emitted as its own reference chunk,
    flagged with reference: True in metadata. These tests validate that
    the reference chunk is correctly identified and separated from the
    dated log entries.
    """

    def test_first_chunk_is_reference(self):
        """
        The first chunk produced from a standard Archetype C note is
        the undated opening block, flagged as reference: True.
        """
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert result[0].metadata.get("reference") is True

    def test_reference_chunk_contains_opening_content(self):
        """The reference chunk contains content from the undated header."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert "Current State" in result[0].chunk_text
        assert "Taltz" in result[0].chunk_text

    def test_reference_chunk_has_no_timestamp(self):
        """The reference chunk has entry_timestamp of None."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert result[0].entry_timestamp is None

    def test_log_chunks_are_not_reference(self):
        """
        Chunks after the reference block do not carry reference: True
        in their metadata.
        """
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        for chunk in result[1:]:
            assert chunk.metadata.get("reference") is not True

    def test_reference_only_note_produces_one_chunk(self):
        """
        A note with only an opening block and no dated log entries
        produces a single reference chunk.
        """
        result = chunk_archetype_c(REFERENCE_ONLY_BODY, CREATED_AT)
        assert len(result) == 1
        assert result[0].metadata.get("reference") is True


# ============================================================================
# LOG SPLITTING TESTS
# ============================================================================


class TestLogSplitting:
    """
    After the reference chunk, the dated log is split on date stamp
    boundaries. These tests validate correct splitting of log entries.
    """

    def test_produces_multiple_chunks_from_standard_note(self):
        """
        A standard note with an opening block and two log entries
        produces more than one chunk.
        """
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert len(result) > 1

    def test_log_content_present_in_output(self):
        """Content from dated log entries appears in the output chunks."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "Injection day" in all_text
        assert "Mild fatigue" in all_text


# ============================================================================
# SUB-TABLE PRESERVATION TESTS
# ============================================================================


class TestSubTablePreservation:
    """
    Embedded markdown tables in the log are kept intact — the chunker
    must not split on dates found inside table rows (lines starting with |).
    """

    def test_table_not_split_on_internal_dates(self):
        """
        Dates inside markdown table rows do not trigger new chunk boundaries.
        The table content should appear intact in a single chunk.
        """
        result = chunk_archetype_c(SUBTABLE_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        # All three table row dates should appear — none triggered a split
        assert "3/1/26" in all_text
        assert "3/8/26" in all_text
        assert "3/15/26" in all_text

    def test_table_rows_appear_in_same_chunk(self):
        """
        All rows of an embedded table appear in the same chunk,
        confirming the table was not split at internal date boundaries.
        """
        result = chunk_archetype_c(SUBTABLE_BODY, CREATED_AT)
        table_chunk = next((c for c in result if "No reaction" in c.chunk_text), None)
        assert table_chunk is not None
        assert "Minor redness" in table_chunk.chunk_text
        assert "Clear" in table_chunk.chunk_text


# ============================================================================
# MERGE BEHAVIOR TESTS
# ============================================================================


class TestMergeBehavior:
    """
    Log entries under MIN_CHUNK_CHARS (~400 chars) are merged with their
    next neighbor. The reference block is never merged with a log entry.
    """

    def test_short_log_entries_are_merged(self):
        """
        A note with four very short log entries produces fewer log chunks
        than entries because short entries are merged with neighbors.
        """
        result = chunk_archetype_c(SHORT_LOG_BODY, CREATED_AT)
        # Reference chunk + merged log chunks — total must be less than 5
        assert len(result) < 5

    def test_reference_chunk_not_merged_with_log(self):
        """
        The reference block is never merged with a log entry regardless
        of its length. It always appears as its own chunk.
        """
        result = chunk_archetype_c(SHORT_LOG_BODY, CREATED_AT)
        assert result[0].metadata.get("reference") is True


# ============================================================================
# TIMESTAMP TESTS
# ============================================================================


class TestTimestamps:
    """
    Log entry timestamps are extracted from date header lines.
    The reference chunk always has entry_timestamp of None.
    """

    def test_log_chunks_have_timestamps(self):
        """
        Log entry chunks have entry_timestamp extracted from their
        date header lines.
        """
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        log_chunks = [c for c in result if not c.metadata.get("reference")]
        assert any(c.entry_timestamp is not None for c in log_chunks)

    def test_reference_chunk_timestamp_is_none(self):
        """The reference chunk always has entry_timestamp of None."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert result[0].entry_timestamp is None


# ============================================================================
# FALLBACK TESTS
# ============================================================================


class TestFallback:
    """
    When no date boundaries are detected, chunk_archetype_c() falls back
    to a single whole-note chunk containing the full body text.
    """

    def test_no_dates_produces_single_chunk(self):
        """A note with no dated log entries falls back to one chunk."""
        result = chunk_archetype_c(NO_DATES_BODY, CREATED_AT)
        assert len(result) == 1

    def test_fallback_chunk_metadata_archetype_c(self):
        """The fallback chunk carries archetype: C in metadata."""
        result = chunk_archetype_c(NO_DATES_BODY, CREATED_AT)
        assert result[0].metadata.get("archetype") == "C"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestEdgeCases:
    """
    Boundary conditions and defensive cases. These tests ensure the chunker
    handles degenerate inputs gracefully without raising exceptions.
    """

    def test_empty_body_does_not_raise(self):
        """Empty body is handled gracefully without exceptions."""
        result = chunk_archetype_c(EMPTY_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_empty_created_at_does_not_raise(self):
        """Empty created_at string is handled gracefully."""
        result = chunk_archetype_c(STANDARD_BODY, "")
        assert isinstance(result, list)

    def test_none_created_at_does_not_raise(self):
        """None created_at is handled gracefully."""
        result = chunk_archetype_c(STANDARD_BODY, None)
        assert isinstance(result, list)

    def test_all_chunks_have_non_negative_char_start(self):
        """char_start is never negative on any chunk."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert all(c.char_start >= 0 for c in result)

    def test_no_empty_chunk_text(self):
        """No chunk has an empty chunk_text string."""
        result = chunk_archetype_c(STANDARD_BODY, CREATED_AT)
        assert all(len(c.chunk_text) > 0 for c in result)
