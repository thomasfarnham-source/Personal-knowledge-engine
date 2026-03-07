"""
Tests for pke/chunking/archetype_d.py

Test strategy:
    - chunk_archetype_d() is tested with representative fixtures covering
      the full range of Archetype D note structures observed in the corpus
    - Tests are organized by behavior: day marker splitting, reference chunk
      emission, resource extraction, timestamp tiers, merge behavior,
      fallback, and chunk shape
    - Fixtures are defined inline as module-level constants

Archetype D — Travel Journal:
    Single note per multi-day trip, written in real time.
    Primary split: day marker boundaries (Day N, day names).
    Pre-trip planning block emitted as its own reference chunk.
    Resource IDs extracted and stripped from chunk text.
    Broken placeholders stripped silently.
    Three-tier timestamp strategy: explicit > calculated > null.
    Merge chunks under MIN_CHUNK_CHARS (~400 chars) with next neighbor.
"""

from pke.chunking.archetype_d import chunk_archetype_d
from pke.chunking.chunk import Chunk

# ============================================================================
# FIXTURES
# ============================================================================

# created_at used for calculated timestamp tests
# Trip note created on 2021-08-29 — Day 1 = 2021-08-29, Day 2 = 2021-08-30
CREATED_AT = "2021-08-29T04:30:00.000Z"

# Representative Archetype D note — pre-trip block + three day entries
# with inline images. Each day entry is long enough to survive merging.
STANDARD_BODY = """
After some consideration we have decided to go to Ireland.
Flights booked for Sunday. Staying in Strandhill with Ger and Killian.
Planning to hike Knocknarea and visit the usual spots along the coast.

Day 1

Arrived in Dublin at 4:30am after a long flight. Ger and Killian
have been here a week already. Drove straight to Strandhill.
Stopped for breakfast in Mullingar — full Irish, much needed.
![IMG_3616.JPG](:/c09c492d04c41e7bef88260a56a8e2f0)
Arrived at the house by noon. Walked down to Flynn's in the evening.
Alan has chickens now which is unexpected and delightful.

Day 2

Slept ten hours. First proper rest in weeks. Walked to the beach
with Killian in the morning — cold but clear, great visibility.
![IMG_3655.HEIC](:/1a461e2ad22f89b2979dd2fd472cdb51)
Lunch at the pub. Caught up properly for the first time in months.
Quiet evening. Early night again to recover from the travel.

Day 3

Beautiful hike up Queen Maeve's Trail in the morning.
Visibility was incredible — could see all the way to Donegal.
Lunch at Strandhill after the hike. Pints deserved.
Long walk on the beach in the evening. Perfect day overall.
""".strip()

# Note with no pre-trip block — starts directly with Day 1
# Entries are padded well above MIN_CHUNK_CHARS (400 chars) each
NO_PREAMBLE_BODY = "\n\n".join([
    "Day 1\n\n" + "Arrived in Dublin at 4:30am. Long flight but worth it. " * 10,
    "Day 2\n\n" + "Slept well. Beach walk in the morning with Killian. " * 10,
])

# Note with day name markers instead of Day N format
DAY_NAME_BODY = """
Heading to Kerry for a long weekend. Should be a great trip.
Booked the house near the beach, looking forward to the walks.

Sunday

Arrived late afternoon. House is perfect — right on the water.
Walked down to the village for dinner. Fresh seafood, excellent.
Early night to recover from the drive down from Dublin.

Monday

Morning hike up the mountain. Views were spectacular at the top.
Packed lunch on the summit. Weather held — rare for Kerry.
Pints in the village pub in the evening. Great atmosphere.
""".strip()

# Note with inline images and audio resources
RESOURCE_BODY = """
Pre-trip notes. Planning the route and accommodation in advance.
Confirmed all bookings. Looking forward to the trip this weekend.

Day 1

Arrived safely. Long journey but good to be here finally.
![IMG_3616.JPG](:/c09c492d04c41e7bef88260a56a8e2f0)
[Evernote 20210829 10:15:50.m4a](:/ee55da041f3e4ff4eb66308a2a89a8d0)
Great to see everyone. Dinner was excellent, caught up well.

Day 2

Full day exploring. Walked for miles along the coastal path.
![IMG_3655.HEIC](:/1a461e2ad22f89b2979dd2fd472cdb51)
Lunch at the harbour. Fresh fish, perfect weather for it.
""".strip()

# Note with broken image placeholders
BROKEN_PLACEHOLDER_BODY = """
Planning notes for the trip. All sorted and ready to go now.
Accommodation confirmed, route planned, packing list complete.

Day 1

Great first day. The scenery was incredible throughout the drive.
{picture)
Stopped at several viewpoints along the way up the coast road.
(Picture)
Dinner at the local restaurant. Highly recommended by the host.

Day 2

Another beautiful day. Walked the full coastal loop this morning.
(picture)
Lunch with the group. Good craic, everyone in great form today.
image
Evening by the fire. Perfect end to a really good second day.
""".strip()

# Note with short day entries that should be merged
SHORT_DAYS_BODY = """
Planning notes for the trip ahead. All confirmed and ready to go.

Day 1

Short first day.

Day 2

Also brief.

Day 3

Another short one.

Day 4

Final short day.
""".strip()

# Note with no day markers — should fall back to single whole-note chunk
NO_MARKERS_BODY = """
We had a wonderful time on this trip. The scenery was beautiful
and the weather was surprisingly good for the time of year.
Everyone was in great form throughout. Would highly recommend
the area to anyone looking for a relaxing break away from the city.
Lots of walking, good food, and excellent company all around.
""".strip()

# Empty body — edge case
EMPTY_BODY = ""


# ============================================================================
# RETURN TYPE TESTS
# ============================================================================


class TestReturnType:
    """
    chunk_archetype_d() always returns a list of Chunk instances.
    These tests validate the return type contract before content assertions.
    """

    def test_returns_list(self):
        """Return value is always a list, never None or a single Chunk."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_returns_chunk_instances(self):
        """Every item in the returned list is a Chunk instance."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c, Chunk) for c in result)

    def test_returns_at_least_one_chunk(self):
        """Non-empty body always produces at least one chunk."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert len(result) >= 1


# ============================================================================
# CHUNK SHAPE TESTS
# ============================================================================


class TestChunkShape:
    """
    Every chunk produced by chunk_archetype_d() must have all required
    fields populated with the correct types and values.
    """

    def test_chunk_indexes_are_sequential(self):
        """chunk_index values are sequential starting from 0."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert [c.chunk_index for c in result] == list(range(len(result)))

    def test_chunk_text_is_non_empty_str(self):
        """chunk_text is a non-empty string on every chunk."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.chunk_text, str) for c in result)
        assert all(len(c.chunk_text) > 0 for c in result)

    def test_chunk_text_is_stripped(self):
        """chunk_text has no leading or trailing whitespace."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert all(c.chunk_text == c.chunk_text.strip() for c in result)

    def test_char_end_greater_than_char_start(self):
        """char_end is always greater than char_start."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert all(c.char_end > c.char_start for c in result)

    def test_metadata_contains_archetype_d(self):
        """Every chunk carries archetype: D in its metadata."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert all(c.metadata.get("archetype") == "D" for c in result)

    def test_metadata_contains_note_type_travel(self):
        """Every chunk carries note_type: travel in its metadata."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert all(c.metadata.get("note_type") == "travel" for c in result)

    def test_resource_ids_is_list(self):
        """resource_ids is always a list on every chunk."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.resource_ids, list) for c in result)


# ============================================================================
# DAY MARKER SPLITTING TESTS
# ============================================================================


class TestDayMarkerSplitting:
    """
    chunk_archetype_d() splits on day marker boundaries. These tests
    validate that Day N markers and day name markers both trigger splits
    and that content from each day appears in the output.
    """

    def test_splits_on_day_n_markers(self):
        """
        A note with three Day N entries plus a pre-trip block produces
        more than one chunk.
        """
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert len(result) > 1

    def test_splits_on_day_name_markers(self):
        """
        Day name markers (Sunday, Monday, etc.) trigger splits just
        like Day N markers.
        """
        result = chunk_archetype_d(DAY_NAME_BODY, CREATED_AT)
        assert len(result) > 1

    def test_content_from_each_day_present(self):
        """Text content from each day entry appears in the output chunks."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "Arrived in Dublin" in all_text
        assert "Slept ten hours" in all_text
        assert "Queen Maeve" in all_text

    def test_note_without_preamble_splits_correctly(self):
        """
        A note starting directly with Day 1 (no pre-trip block) still
        splits correctly on day boundaries.
        """
        result = chunk_archetype_d(NO_PREAMBLE_BODY, CREATED_AT)
        assert len(result) > 1


# ============================================================================
# REFERENCE CHUNK TESTS
# ============================================================================


class TestReferenceChunk:
    """
    The pre-trip planning block (content before the first day marker)
    is emitted as its own reference chunk flagged with reference: True.
    """

    def test_pre_trip_block_is_reference_chunk(self):
        """
        The first chunk from a note with a pre-trip block is flagged
        as reference: True in metadata.
        """
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert result[0].metadata.get("reference") is True

    def test_reference_chunk_contains_pre_trip_content(self):
        """The reference chunk contains content from the pre-trip block."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert "decided to go to Ireland" in result[0].chunk_text

    def test_day_chunks_are_not_reference(self):
        """Day entry chunks do not carry reference: True in metadata."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        for chunk in result[1:]:
            assert chunk.metadata.get("reference") is not True


# ============================================================================
# RESOURCE EXTRACTION TESTS
# ============================================================================


class TestResourceExtraction:
    """
    Resource IDs are extracted from image and audio links and stored in
    resource_ids. Resource references are stripped from chunk text.
    Broken placeholders are stripped silently with no ID stored.
    """

    def test_image_resource_ids_extracted(self):
        """
        Markdown image resource IDs are extracted into resource_ids
        on the chunk containing the image reference.
        """
        result = chunk_archetype_d(RESOURCE_BODY, CREATED_AT)
        all_ids = [rid for c in result for rid in c.resource_ids]
        assert "c09c492d04c41e7bef88260a56a8e2f0" in all_ids
        assert "1a461e2ad22f89b2979dd2fd472cdb51" in all_ids

    def test_audio_resource_ids_extracted(self):
        """
        Audio link resource IDs are extracted into resource_ids
        on the chunk containing the audio reference.
        """
        result = chunk_archetype_d(RESOURCE_BODY, CREATED_AT)
        all_ids = [rid for c in result for rid in c.resource_ids]
        assert "ee55da041f3e4ff4eb66308a2a89a8d0" in all_ids

    def test_resource_references_stripped_from_chunk_text(self):
        """
        Image and audio resource references are removed from chunk text.
        Resource IDs should not appear inline in clean_text.
        """
        result = chunk_archetype_d(RESOURCE_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert ":/c09c492d04c41e7bef88260a56a8e2f0" not in all_text
        assert ":/ee55da041f3e4ff4eb66308a2a89a8d0" not in all_text

    def test_broken_placeholders_stripped_silently(self):
        """
        Broken image placeholders are stripped from chunk text without
        storing any resource ID.
        """
        result = chunk_archetype_d(BROKEN_PLACEHOLDER_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "{picture)" not in all_text
        assert "(Picture)" not in all_text
        assert "(picture)" not in all_text

    def test_no_resource_ids_from_broken_placeholders(self):
        """
        Broken placeholders produce no entries in resource_ids.
        """
        result = chunk_archetype_d(BROKEN_PLACEHOLDER_BODY, CREATED_AT)
        all_ids = [rid for c in result for rid in c.resource_ids]
        assert all_ids == []

    def test_prose_preserved_after_resource_stripping(self):
        """
        Non-resource prose content is preserved after resource references
        are stripped from chunk text.
        """
        result = chunk_archetype_d(RESOURCE_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "Arrived safely" in all_text
        assert "Full day exploring" in all_text


# ============================================================================
# TIMESTAMP TESTS
# ============================================================================


class TestTimestamps:
    """
    Three-tier timestamp strategy: explicit date in text → calculated
    from created_at + day offset → None. These tests validate each tier.
    """

    def test_calculated_timestamps_use_created_at(self):
        """
        When no explicit date is found, timestamps are calculated from
        created_at + day offset and prefixed with 'calculated: '.
        """
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        day_chunks = [c for c in result if not c.metadata.get("reference")]
        calculated = [
            c.entry_timestamp for c in day_chunks
            if c.entry_timestamp and c.entry_timestamp.startswith("calculated:")
        ]
        assert len(calculated) > 0

    def test_calculated_timestamp_format(self):
        """
        Calculated timestamps follow the format 'calculated: YYYY-MM-DD'.
        """
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        day_chunks = [c for c in result if not c.metadata.get("reference")]
        for chunk in day_chunks:
            if chunk.entry_timestamp and chunk.entry_timestamp.startswith("calculated:"):
                assert chunk.entry_timestamp.startswith("calculated: 20")

    def test_reference_chunk_may_have_null_timestamp(self):
        """
        The pre-trip reference chunk typically has no explicit date
        and may have entry_timestamp of None.
        """
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        ref_chunk = result[0]
        # Reference chunk timestamp is None or a calculated value —
        # either is valid depending on whether a date appears in the text
        assert ref_chunk.entry_timestamp is None or isinstance(
            ref_chunk.entry_timestamp, str
        )


# ============================================================================
# MERGE BEHAVIOR TESTS
# ============================================================================


class TestMergeBehavior:
    """
    Day chunks under MIN_CHUNK_CHARS (~400 chars) are merged with their
    next neighbor. The reference chunk is never merged with a day chunk.
    """

    def test_short_day_entries_are_merged(self):
        """
        A note with four very short day entries produces fewer chunks
        than entries because short entries are merged with neighbors.
        """
        result = chunk_archetype_d(SHORT_DAYS_BODY, CREATED_AT)
        # Reference chunk + merged day chunks — total must be less than 5
        assert len(result) < 5

    def test_reference_chunk_not_merged_with_day_entries(self):
        """
        The reference block is never merged with a day entry regardless
        of its length. It always appears as its own chunk.
        """
        result = chunk_archetype_d(SHORT_DAYS_BODY, CREATED_AT)
        assert result[0].metadata.get("reference") is True


# ============================================================================
# FALLBACK TESTS
# ============================================================================


class TestFallback:
    """
    When no day markers are detected, chunk_archetype_d() falls back
    to a single whole-note chunk containing the full body text.
    """

    def test_no_markers_produces_single_chunk(self):
        """A note with no day markers falls back to one whole-note chunk."""
        result = chunk_archetype_d(NO_MARKERS_BODY, CREATED_AT)
        assert len(result) == 1

    def test_fallback_chunk_metadata_archetype_d(self):
        """The fallback chunk carries archetype: D and note_type: travel."""
        result = chunk_archetype_d(NO_MARKERS_BODY, CREATED_AT)
        assert result[0].metadata.get("archetype") == "D"
        assert result[0].metadata.get("note_type") == "travel"


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
        result = chunk_archetype_d(EMPTY_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_empty_created_at_does_not_raise(self):
        """Empty created_at string is handled gracefully."""
        result = chunk_archetype_d(STANDARD_BODY, "")
        assert isinstance(result, list)

    def test_none_created_at_does_not_raise(self):
        """None created_at is handled gracefully."""
        result = chunk_archetype_d(STANDARD_BODY, None)
        assert isinstance(result, list)

    def test_all_chunks_have_non_negative_char_start(self):
        """char_start is never negative on any chunk."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert all(c.char_start >= 0 for c in result)

    def test_no_empty_chunk_text(self):
        """No chunk has an empty chunk_text string."""
        result = chunk_archetype_d(STANDARD_BODY, CREATED_AT)
        assert all(len(c.chunk_text) > 0 for c in result)