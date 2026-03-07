"""
Tests for pke/chunking/archetype_b.py

Test strategy:
    - chunk_archetype_b() is tested with representative fixtures covering
      the full range of Archetype B note structures observed in the corpus
    - Tests are organized by behavior: splitting, secondary splits on
      template headers, merging, timestamps, fallback, and chunk shape
    - Fixtures are defined inline as module-level constants

Archetype B — Structured Journal:
    Long entries of 200-500 words with consistent internal template.
    Template sections: Score, What did I do well, Improvements, Gratitude.
    Primary split: date stamps. Secondary split: template section headers
    for entries exceeding MAX_CHUNK_CHARS (~2000 chars).
    Merge entries under MIN_CHUNK_CHARS (~400 chars) with next neighbor.
"""

from pke.chunking.archetype_b import chunk_archetype_b
from pke.chunking.chunk import Chunk

# ============================================================================
# FIXTURES
# ============================================================================

# Standard created_at timestamp used across tests
CREATED_AT = "2019-03-15T00:00:00.000Z"

# Representative Archetype B note — two dated entries with template sections
# Each entry is above MIN_CHUNK_CHARS but below MAX_CHUNK_CHARS
STANDARD_BODY = """
## 2019-03-15

### Score
7

### What did I do well
Stayed focused in the morning. Good conversation with Killian.
Finished the report ahead of schedule. Exercised before lunch.
The meeting went well and everyone was aligned on next steps.
Spent quality time in the evening reading and unwinding properly.

### Improvements
Should have gone to bed earlier. Spent too long on email.
Need to be more disciplined about the afternoon slump.
Could have communicated better on the project status update.

### Gratitude
Ger, the weather, good health, the project going well.
Grateful for the team pulling together this week.
Thankful for the good conversation with Killian over lunch.

## 2019-03-16

### Score
8

### What did I do well
Great session at the gym. Clear thinking all day.
Finished two tasks that had been hanging for a week.
Good energy throughout the afternoon, stayed off social media.
Had a productive call with the client — things are moving forward.

### Improvements
Distracted in the afternoon. Should have taken a break sooner.
Need to follow up on the email I keep putting off.
Could plan the next day better before going to bed.

### Gratitude
Good sleep, Killian's advice, the sunshine.
Grateful for the clarity I had today on the big decision.
Thankful for the support from Ger this week.
""".strip()

# Note with a single dated entry — no splitting needed
SINGLE_ENTRY_BODY = """
## 2019-03-15

### Score
8

### What did I do well
Really focused day. Got through the whole task list.
Called mom in the evening. She sounded great.

### Improvements
Could have been more present at dinner.

### Gratitude
Health, family, the project moving forward.
""".strip()

# Note with short entries that should be merged
SHORT_ENTRIES_BODY = """
## 2019-03-15

Short entry. Not much happened.

## 2019-03-16

Also brief. Quiet day.

## 2019-03-17

Another short one. Stayed home.

## 2019-03-18

Final short entry. Early night.
""".strip()

# Note with a very long entry that should trigger secondary split
# on template section headers
LONG_ENTRY_BODY = (
    "## 2019-03-15\n\n"
    "### Score\n7\n\n"
    "### What did I do well\n" + "Had a really productive day. " * 40 + "\n\n"
    "### Improvements\n" + "Should have taken more breaks. " * 40 + "\n\n"
    "### Gratitude\n" + "Grateful for many things today. " * 40
)

# Note with no date stamps — should fall back to single whole-note chunk
NO_DATES_BODY = """
### Score
7

### What did I do well
Good focus today. Got a lot done.

### Improvements
Should exercise more consistently.

### Gratitude
Health, family, good weather.
""".strip()

# Empty body — edge case
EMPTY_BODY = ""


# ============================================================================
# RETURN TYPE TESTS
# ============================================================================


class TestReturnType:
    """
    chunk_archetype_b() always returns a list of Chunk instances.
    These tests validate the return type contract before any content
    assertions.
    """

    def test_returns_list(self):
        """Return value is always a list, never None or a single Chunk."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_returns_chunk_instances(self):
        """Every item in the returned list is a Chunk instance."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c, Chunk) for c in result)

    def test_returns_at_least_one_chunk(self):
        """Non-empty body always produces at least one chunk."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert len(result) >= 1


# ============================================================================
# CHUNK SHAPE TESTS
# ============================================================================


class TestChunkShape:
    """
    Every chunk produced by chunk_archetype_b() must have all required
    fields populated with the correct types and values.
    """

    def test_chunk_index_is_int(self):
        """chunk_index is an integer on every chunk."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.chunk_index, int) for c in result)

    def test_chunk_indexes_are_sequential(self):
        """chunk_index values are sequential starting from 0."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert [c.chunk_index for c in result] == list(range(len(result)))

    def test_chunk_text_is_non_empty_str(self):
        """chunk_text is a non-empty string on every chunk."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.chunk_text, str) for c in result)
        assert all(len(c.chunk_text) > 0 for c in result)

    def test_chunk_text_is_stripped(self):
        """chunk_text has no leading or trailing whitespace."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert all(c.chunk_text == c.chunk_text.strip() for c in result)

    def test_char_end_greater_than_char_start(self):
        """char_end is always greater than char_start."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert all(c.char_end > c.char_start for c in result)

    def test_metadata_contains_archetype_b(self):
        """Every chunk carries archetype: B in its metadata."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert all(c.metadata.get("archetype") == "B" for c in result)

    def test_resource_ids_is_empty_list(self):
        """
        Archetype B notes do not contain resource references.
        resource_ids should always be an empty list.
        """
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert all(c.resource_ids == [] for c in result)


# ============================================================================
# SPLITTING TESTS
# ============================================================================


class TestSplitting:
    """
    chunk_archetype_b() splits primarily on date stamp boundaries.
    These tests validate that entries are correctly separated and that
    content from each entry appears in the output chunks.
    """

    def test_splits_on_date_boundaries(self):
        """
        A note with two dated entries produces multiple chunks.
        The exact count depends on merge behavior but must be more than one.
        """
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert len(result) > 1

    def test_content_from_each_entry_present(self):
        """Text content from each dated entry appears in the output chunks."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "Stayed focused in the morning" in all_text
        assert "Great session at the gym" in all_text

    def test_single_entry_produces_one_chunk(self):
        """A note with a single dated entry produces exactly one chunk."""
        result = chunk_archetype_b(SINGLE_ENTRY_BODY, CREATED_AT)
        assert len(result) == 1

    def test_template_headers_preserved_in_chunk_text(self):
        """
        Template section headers (Score, What did I do well, etc.) are
        preserved in chunk text — they are content, not stripped.
        """
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "Score" in all_text
        assert "What did I do well" in all_text
        assert "Gratitude" in all_text


# ============================================================================
# SECONDARY SPLIT TESTS
# ============================================================================


class TestSecondarySplit:
    """
    Entries exceeding MAX_CHUNK_CHARS (~2000 chars) are split further
    on template section headers. These tests validate that the secondary
    split fires correctly for long entries.
    """

    def test_long_entry_produces_multiple_chunks(self):
        """
        A single dated entry exceeding MAX_CHUNK_CHARS is split on
        template section headers into multiple chunks.
        """
        result = chunk_archetype_b(LONG_ENTRY_BODY, CREATED_AT)
        assert len(result) > 1

    def test_secondary_split_chunks_contain_section_content(self):
        """
        Each chunk from a secondary split contains content from its
        corresponding template section.
        """
        result = chunk_archetype_b(LONG_ENTRY_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "Had a really productive day" in all_text
        assert "Should have taken more breaks" in all_text
        assert "Grateful for many things today" in all_text


# ============================================================================
# MERGE BEHAVIOR TESTS
# ============================================================================


class TestMergeBehavior:
    """
    Entries under MIN_CHUNK_CHARS (~400 chars) are merged with their
    next neighbor. These tests validate the merge logic for short entries.
    """

    def test_short_entries_are_merged(self):
        """
        A note with four very short entries produces fewer chunks than
        entries because short entries are merged with their neighbors.
        """
        result = chunk_archetype_b(SHORT_ENTRIES_BODY, CREATED_AT)
        assert len(result) < 4

    def test_merged_chunk_contains_content_from_both_entries(self):
        """
        A merged chunk contains text from both the short entry and
        its neighbor.
        """
        result = chunk_archetype_b(SHORT_ENTRIES_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "2019-03-15" in all_text
        assert "2019-03-16" in all_text


# ============================================================================
# TIMESTAMP TESTS
# ============================================================================


class TestTimestamps:
    """
    Timestamps are extracted from date header lines using parse_date().
    These tests validate correct timestamp extraction for Archetype B
    ISO format date headers.
    """

    def test_timestamps_extracted_from_date_headers(self):
        """
        entry_timestamp is set from the date header line for each chunk.
        ISO format (## 2019-03-15) should parse to YYYY-MM-DD.
        """
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        timestamps = [c.entry_timestamp for c in result]
        assert any(t is not None for t in timestamps)

    def test_iso_date_parses_correctly(self):
        """## 2019-03-15 header parses to entry_timestamp 2019-03-15."""
        result = chunk_archetype_b(SINGLE_ENTRY_BODY, CREATED_AT)
        assert result[0].entry_timestamp == "2019-03-15"

    def test_undated_note_has_none_timestamp(self):
        """
        A note with no date stamps produces a chunk with
        entry_timestamp of None.
        """
        result = chunk_archetype_b(NO_DATES_BODY, CREATED_AT)
        assert result[0].entry_timestamp is None


# ============================================================================
# FALLBACK TESTS
# ============================================================================


class TestFallback:
    """
    When no date boundaries are detected, chunk_archetype_b() falls back
    to a single whole-note chunk containing the full body text.
    """

    def test_no_dates_produces_single_chunk(self):
        """A note with no date stamps falls back to one whole-note chunk."""
        result = chunk_archetype_b(NO_DATES_BODY, CREATED_AT)
        assert len(result) == 1

    def test_fallback_chunk_contains_full_body(self):
        """The fallback chunk contains the full note body text."""
        result = chunk_archetype_b(NO_DATES_BODY, CREATED_AT)
        assert result[0].chunk_text == NO_DATES_BODY.strip()

    def test_fallback_chunk_metadata_archetype_b(self):
        """The fallback chunk carries archetype: B in metadata."""
        result = chunk_archetype_b(NO_DATES_BODY, CREATED_AT)
        assert result[0].metadata.get("archetype") == "B"


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
        result = chunk_archetype_b(EMPTY_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_empty_created_at_does_not_raise(self):
        """Empty created_at string is handled gracefully."""
        result = chunk_archetype_b(STANDARD_BODY, "")
        assert isinstance(result, list)

    def test_none_created_at_does_not_raise(self):
        """None created_at is handled gracefully."""
        result = chunk_archetype_b(STANDARD_BODY, None)
        assert isinstance(result, list)

    def test_all_chunks_have_non_negative_char_start(self):
        """char_start is never negative on any chunk."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert all(c.char_start >= 0 for c in result)

    def test_no_empty_chunk_text(self):
        """No chunk has an empty chunk_text string."""
        result = chunk_archetype_b(STANDARD_BODY, CREATED_AT)
        assert all(len(c.chunk_text) > 0 for c in result)
