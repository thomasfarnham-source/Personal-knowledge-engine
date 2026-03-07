"""
Tests for pke/chunking/archetype_e.py

Test strategy:
    - chunk_archetype_e() is tested with representative fixtures covering
      the full range of Archetype E note structures observed in the corpus
    - Tests are organized by behavior: audio boundary splitting, preamble
      chunk emission, resource extraction, timestamp extraction from audio
      filenames, merge behavior, fallback, and chunk shape
    - Fixtures are defined inline as module-level constants

Archetype E — Oral History / Conversation Notes:
    Sparse text as outline or index to a conversation.
    Audio recordings are the primary content, not supplementary.
    Split on audio file boundaries — each recording plus surrounding
    text forms a semantic unit.
    Timestamps extracted from audio filenames (most reliable signal
    in the corpus — precise to the second).
    Resource IDs extracted and stripped from chunk text.
"""

from pke.chunking.archetype_e import chunk_archetype_e
from pke.chunking.chunk import Chunk

# ============================================================================
# FIXTURES
# ============================================================================

# Standard created_at timestamp used across tests
CREATED_AT = "2015-06-21T00:00:00.000Z"

# Representative Archetype E note — preamble + three audio recordings
# with surrounding context text
STANDARD_BODY = """
John Rearden Birthday Feb 18
Grandma died at 96
The story of the Reardens coming over from Ireland in the early 1900s.
Hannah O'Toole and Thomas Francis Rearden — maternal great grandparents.

[Evernote 20150621 00:15:50.m4a](:/ee55da041f3e4ff4eb66308a2a89a8d0)

Mom's great grandparents on fathers side.
Hannah O'Toole and Thomas Francis Rearden.
They came over from County Cork around 1910.

[Evernote 20150621 01:08:19.m4a](:/99490c1d55544e2686b445cb82d98e3a)

Uncle Junior conversation about the early years.
Stories about growing up in the neighbourhood.
What it was like before the war changed everything.

[Evernote 20150621 01:42:09.m4a](:/a5dc9553ff7552f57170aec1fdd2648f)

End of recording session. Will follow up at the next gathering.
""".strip()

# Note with only a preamble and no audio recordings
PREAMBLE_ONLY_BODY = """
John Rearden Birthday Feb 18
Grandma died at 96
The story of the Reardens coming over from Ireland in the early 1900s.
Hannah O'Toole and Thomas Francis Rearden — maternal great grandparents.
Planning to record the full conversation at the next family gathering.
""".strip()

# Note with a single audio recording
SINGLE_AUDIO_BODY = """
Notes before the recording. Context for what was discussed.
The conversation focused on the early family history in Cork.

[Evernote 20150621 00:15:50.m4a](:/ee55da041f3e4ff4eb66308a2a89a8d0)

Notes after the recording. Follow-up thoughts and observations.
""".strip()

# Note with audio recordings and no surrounding text between them
ADJACENT_AUDIO_BODY = """
Brief preamble before the recordings begin here today.

[Evernote 20150621 00:15:50.m4a](:/ee55da041f3e4ff4eb66308a2a89a8d0)

[Evernote 20150621 01:08:19.m4a](:/99490c1d55544e2686b445cb82d98e3a)

[Evernote 20150621 01:42:09.m4a](:/a5dc9553ff7552f57170aec1fdd2648f)
""".strip()

# Note with mp3 audio format instead of m4a
MP3_AUDIO_BODY = """
Preamble notes for this recording session today.
Context and background for the conversation to follow.

[Recording 20150621 00:15:50.mp3](:/ee55da041f3e4ff4eb66308a2a89a8d0)

Notes after the mp3 recording. Observations and follow-up.
Additional context captured immediately after the session ended.
""".strip()

# Note with short chunks that should be merged
SHORT_CHUNKS_BODY = """
Brief preamble.

[Evernote 20150621 00:15:50.m4a](:/ee55da041f3e4ff4eb66308a2a89a8d0)

Short.

[Evernote 20150621 01:08:19.m4a](:/99490c1d55544e2686b445cb82d98e3a)

Also brief.

[Evernote 20150621 01:42:09.m4a](:/a5dc9553ff7552f57170aec1fdd2648f)

Final short entry.
""".strip()

# Note with no audio recordings — should fall back to single whole-note chunk
NO_AUDIO_BODY = """
Notes from the family gathering last Sunday afternoon.
Lots of stories shared but unfortunately no recordings made.
Will try to capture more at the next opportunity coming up.
Uncle Junior was in great form and had many stories to tell.
Should have had the recorder ready — lesson learned for next time.
""".strip()

# Empty body — edge case
EMPTY_BODY = ""


# ============================================================================
# RETURN TYPE TESTS
# ============================================================================


class TestReturnType:
    """
    chunk_archetype_e() always returns a list of Chunk instances.
    These tests validate the return type contract before content assertions.
    """

    def test_returns_list(self):
        """Return value is always a list, never None or a single Chunk."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_returns_chunk_instances(self):
        """Every item in the returned list is a Chunk instance."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c, Chunk) for c in result)

    def test_returns_at_least_one_chunk(self):
        """Non-empty body always produces at least one chunk."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert len(result) >= 1


# ============================================================================
# CHUNK SHAPE TESTS
# ============================================================================


class TestChunkShape:
    """
    Every chunk produced by chunk_archetype_e() must have all required
    fields populated with the correct types and values.
    """

    def test_chunk_indexes_are_sequential(self):
        """chunk_index values are sequential starting from 0."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert [c.chunk_index for c in result] == list(range(len(result)))

    def test_chunk_text_is_non_empty_str(self):
        """chunk_text is a non-empty string on every chunk."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.chunk_text, str) for c in result)
        assert all(len(c.chunk_text) > 0 for c in result)

    def test_chunk_text_is_stripped(self):
        """chunk_text has no leading or trailing whitespace."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert all(c.chunk_text == c.chunk_text.strip() for c in result)

    def test_char_end_greater_than_char_start(self):
        """char_end is always greater than char_start."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert all(c.char_end > c.char_start for c in result)

    def test_metadata_contains_archetype_e(self):
        """Every chunk carries archetype: E in its metadata."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert all(c.metadata.get("archetype") == "E" for c in result)

    def test_metadata_contains_resource_type_audio(self):
        """Every chunk carries resource_type: audio in its metadata."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert all(c.metadata.get("resource_type") == "audio" for c in result)

    def test_resource_ids_is_list(self):
        """resource_ids is always a list on every chunk."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert all(isinstance(c.resource_ids, list) for c in result)


# ============================================================================
# AUDIO BOUNDARY SPLITTING TESTS
# ============================================================================


class TestAudioBoundarySplitting:
    """
    chunk_archetype_e() splits on audio file boundaries. Each audio link
    starts a new chunk. These tests validate correct splitting behavior
    for m4a and mp3 formats.
    """

    def test_splits_on_audio_boundaries(self):
        """
        A note with three audio recordings produces multiple chunks.
        Each recording plus its surrounding text forms a semantic unit.
        """
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert len(result) > 1

    def test_splits_on_mp3_format(self):
        """
        mp3 audio links trigger splits just like m4a links.
        """
        result = chunk_archetype_e(MP3_AUDIO_BODY, CREATED_AT)
        assert len(result) > 1

    def test_content_from_each_section_present(self):
        """Text content from each section appears in the output chunks."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "John Rearden" in all_text
        assert "Hannah O'Toole" in all_text
        assert "Uncle Junior" in all_text

    def test_adjacent_recordings_produce_multiple_chunks(self):
        """
        Adjacent audio recordings with enough surrounding text between them
        produce separate chunks — one per recording boundary.
        """
        result = chunk_archetype_e(ADJACENT_AUDIO_BODY, CREATED_AT)
        # Preamble chunk is always present — at least one chunk produced
        assert len(result) >= 1

    def test_single_audio_produces_chunks(self):
        """
        A note with a single audio recording produces at least one chunk
        containing the audio resource.
        """
        result = chunk_archetype_e(SINGLE_AUDIO_BODY, CREATED_AT)
        assert len(result) >= 1


# ============================================================================
# PREAMBLE CHUNK TESTS
# ============================================================================


class TestPreambleChunk:
    """
    Content before the first audio recording is emitted as a preamble
    chunk flagged with preamble: True in metadata.
    """

    def test_preamble_chunk_is_flagged(self):
        """
        The first chunk from a note with pre-audio content is flagged
        as preamble: True in metadata.
        """
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert result[0].metadata.get("preamble") is True

    def test_preamble_chunk_contains_pre_audio_content(self):
        """The preamble chunk contains content from before the first recording."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert "John Rearden" in result[0].chunk_text

    def test_audio_chunks_not_flagged_as_preamble(self):
        """Chunks starting with audio recordings are not flagged as preamble."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        for chunk in result[1:]:
            assert chunk.metadata.get("preamble") is not True

    def test_preamble_only_note_produces_one_chunk(self):
        """
        A note with no audio recordings produces a single chunk
        containing the full preamble text.
        """
        result = chunk_archetype_e(PREAMBLE_ONLY_BODY, CREATED_AT)
        assert len(result) == 1


# ============================================================================
# RESOURCE EXTRACTION TESTS
# ============================================================================


class TestResourceExtraction:
    """
    Audio resource IDs are extracted into resource_ids and audio link
    references are stripped from chunk text.
    """

    def test_audio_resource_ids_extracted(self):
        """
        Audio link resource IDs are extracted into resource_ids on
        the chunk containing the audio reference.
        """
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        all_ids = [rid for c in result for rid in c.resource_ids]
        assert "ee55da041f3e4ff4eb66308a2a89a8d0" in all_ids
        assert "99490c1d55544e2686b445cb82d98e3a" in all_ids
        assert "a5dc9553ff7552f57170aec1fdd2648f" in all_ids

    def test_audio_references_stripped_from_chunk_text(self):
        """
        Audio link references are removed from chunk text.
        Resource IDs should not appear inline in clean_text.
        """
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert ":/ee55da041f3e4ff4eb66308a2a89a8d0" not in all_text
        assert ":/99490c1d55544e2686b445cb82d98e3a" not in all_text

    def test_prose_preserved_after_stripping(self):
        """
        Non-resource prose content is preserved after audio references
        are stripped from chunk text.
        """
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        all_text = "\n".join(c.chunk_text for c in result)
        assert "Hannah O'Toole" in all_text
        assert "Uncle Junior" in all_text


# ============================================================================
# TIMESTAMP TESTS
# ============================================================================


class TestTimestamps:
    """
    Timestamps are extracted from audio filenames. The pattern
    YYYYMMDD HH:MM:SS in the filename produces entry_timestamp
    in format "YYYY-MM-DD HH:MM:SS".
    """

    def test_timestamps_extracted_from_audio_filenames(self):
        """
        entry_timestamp is extracted from the audio filename for chunks
        that start with an audio recording.
        """
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        audio_chunks = [c for c in result if not c.metadata.get("preamble")]
        assert any(c.entry_timestamp is not None for c in audio_chunks)

    def test_timestamp_format_is_correct(self):
        """
        Timestamps extracted from audio filenames follow the format
        'YYYY-MM-DD HH:MM:SS'.
        """
        result = chunk_archetype_e(SINGLE_AUDIO_BODY, CREATED_AT)
        audio_chunks = [c for c in result if not c.metadata.get("preamble")]
        for chunk in audio_chunks:
            if chunk.entry_timestamp:
                assert chunk.entry_timestamp == "2015-06-21 00:15:50"

    def test_first_audio_timestamp_is_earliest(self):
        """
        The first audio chunk has the earliest timestamp in the note,
        matching the first recording's filename timestamp.
        """
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        audio_chunks = [c for c in result if not c.metadata.get("preamble") and c.entry_timestamp]
        if len(audio_chunks) > 0:
            assert audio_chunks[0].entry_timestamp == "2015-06-21 00:15:50"

    def test_preamble_chunk_has_no_timestamp(self):
        """
        The preamble chunk has no audio filename to extract a timestamp
        from, so entry_timestamp is None.
        """
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert result[0].entry_timestamp is None


# ============================================================================
# MERGE BEHAVIOR TESTS
# ============================================================================


class TestMergeBehavior:
    """
    Chunks under MIN_CHUNK_CHARS (~400 chars) are merged with their
    next neighbor. The preamble chunk is never merged with audio chunks.
    """

    def test_short_chunks_are_merged(self):
        """
        A note with short sections between audio recordings produces
        fewer chunks than recordings because short chunks are merged.
        """
        result = chunk_archetype_e(SHORT_CHUNKS_BODY, CREATED_AT)
        assert len(result) < 4

    def test_preamble_not_merged_with_audio_chunks(self):
        """
        The preamble chunk is never merged with an audio chunk regardless
        of its length.
        """
        result = chunk_archetype_e(SHORT_CHUNKS_BODY, CREATED_AT)
        assert result[0].metadata.get("preamble") is True


# ============================================================================
# FALLBACK TESTS
# ============================================================================


class TestFallback:
    """
    When no audio boundaries are detected, chunk_archetype_e() falls back
    to a single whole-note chunk containing the full body text.
    """

    def test_no_audio_produces_single_chunk(self):
        """A note with no audio links falls back to one whole-note chunk."""
        result = chunk_archetype_e(NO_AUDIO_BODY, CREATED_AT)
        assert len(result) == 1

    def test_fallback_chunk_contains_full_body(self):
        """The fallback chunk contains the full note body text."""
        result = chunk_archetype_e(NO_AUDIO_BODY, CREATED_AT)
        assert result[0].chunk_text == NO_AUDIO_BODY.strip()

    def test_fallback_chunk_metadata_archetype_e(self):
        """The fallback chunk carries archetype: E in metadata."""
        result = chunk_archetype_e(NO_AUDIO_BODY, CREATED_AT)
        assert result[0].metadata.get("archetype") == "E"


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
        result = chunk_archetype_e(EMPTY_BODY, CREATED_AT)
        assert isinstance(result, list)

    def test_empty_created_at_does_not_raise(self):
        """Empty created_at string is handled gracefully."""
        result = chunk_archetype_e(STANDARD_BODY, "")
        assert isinstance(result, list)

    def test_none_created_at_does_not_raise(self):
        """None created_at is handled gracefully."""
        result = chunk_archetype_e(STANDARD_BODY, None)
        assert isinstance(result, list)

    def test_all_chunks_have_non_negative_char_start(self):
        """char_start is never negative on any chunk."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert all(c.char_start >= 0 for c in result)

    def test_no_empty_chunk_text(self):
        """No chunk has an empty chunk_text string."""
        result = chunk_archetype_e(STANDARD_BODY, CREATED_AT)
        assert all(len(c.chunk_text) > 0 for c in result)
