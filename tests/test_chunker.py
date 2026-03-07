"""
Tests for pke/chunking/chunker.py

Test strategy:
    - detect_archetype() is tested independently with representative fixtures
      for each archetype, including edge cases and metadata hints
    - chunk_note() is tested for threshold behavior and correct dispatch
    - Each archetype chunker is tested with a real-world representative sample
      drawn from the actual corpus note analysis

Fixtures are defined inline as module-level constants so they are readable
and maintainable without external files.

Note: archetype chunker implementations are currently placeholders — tests
assert on the placeholder output shape and metadata. When real implementations
replace the placeholders, the assertions will be updated accordingly.
"""

from pke.chunking.chunker import Chunk, chunk_note, detect_archetype

# ============================================================================
# FIXTURES — REPRESENTATIVE CORPUS SAMPLES
# ============================================================================

# Archetype A — Fragmented journal: short entries, date stamps only
ARCHETYPE_A_BODY = """
1/3/19

Went to the gym. Read for an hour.

1/4/19

Skipped gym. Tired.

1/5/19

Good day. Productive at work. Called dad.
""".strip()

# Archetype B — Structured journal: template section headers
ARCHETYPE_B_BODY = """
## 2019-03-15

Score: 7

### What did I do well
Stayed focused in the morning. Good conversation with Killian.

### Improvements
Should have gone to bed earlier.

### Gratitude
Ger, the weather, good health.
""".strip()

# Archetype C — Reference/medical log: undated header + dated log
ARCHETYPE_C_BODY = """
## Current State
Currently on Taltz injection every 8 weeks. Managing well.
Last blood work normal. Next appointment March 2026.

---

## Log

### 1/15/26
Injection day. No side effects.

### 11/20/25
Mild fatigue for two days post-injection.
""".strip()

# Archetype D — Travel journal: day markers, images, written in real time
ARCHETYPE_D_BODY = """
After some consideration we have decided to go to Ireland.

Day 1

Arrived in Dublin at 4:30am. Ger and Killian have been here a week.

![IMG_3616.JPG](:/c09c492d04c41e7bef88260a56a8e2f0)

Day 2

Slept 10 hours. Walked down to Flynn's with K. Alan has chickens now.

![IMG_3655.HEIC](:/1a461e2ad22f89b2979dd2fd472cdb51)

Day 3

Beautiful hike up Queen Maeve's Trail. Lunch at Strandhill after.
""".strip()

# Archetype E — Oral history: audio recordings as primary content
ARCHETYPE_E_BODY = """
John Rearden Birthday Feb 18
Grandma died at 96
The story of reardens coming from Ireland.

[Evernote 20150621 00:15:50.m4a](:/ee55da041f3e4ff4eb66308a2a89a8d0)

Mom's great grandparents on fathers side.
Hannah o'toole and Thomas Francis Rearden.

[Evernote 20150621 01:08:19.m4a](:/99490c1d55544e2686b445cb82d98e3a)

Uncle junior conversation.

[Evernote 20150621 01:42:09.m4a](:/a5dc9553ff7552f57170aec1fdd2648f)
""".strip()

# A short note that should never be chunked (below threshold)
SHORT_BODY = "Quick note. Buy milk."

# Created-at timestamp used for Archetype D calculated date tests
CREATED_AT = "2021-08-29T04:30:00.000Z"


# ============================================================================
# detect_archetype() TESTS
# ============================================================================


class TestDetectArchetype:
    """
    Tests for archetype detection logic.

    Each test targets one archetype with a representative body.
    Edge cases test that metadata hints override ambiguous text patterns.
    """

    def test_detects_archetype_e_from_audio_link(self):
        """Audio resource link is the strongest signal — detected before all others."""
        assert detect_archetype(ARCHETYPE_E_BODY) == "E"

    def test_detects_archetype_d_from_day_markers(self):
        """Explicit Day N markers in body trigger Archetype D detection."""
        assert detect_archetype(ARCHETYPE_D_BODY) == "D"

    def test_detects_archetype_d_from_title_hint(self):
        """Title containing 'ireland' triggers Archetype D even without day markers."""
        assert detect_archetype("Some prose with no day markers.", title="Ireland 2021") == "D"

    def test_detects_archetype_d_from_notebook_hint(self):
        """Notebook named 'Travel' triggers Archetype D even without day markers."""
        assert detect_archetype("Some prose with no day markers.", notebook="Travel") == "D"

    def test_detects_archetype_c_from_undated_header_and_log(self):
        """Undated opening block followed by dated section headers → Archetype C."""
        assert detect_archetype(ARCHETYPE_C_BODY) == "C"

    def test_detects_archetype_b_from_template_headers(self):
        """Structured template section headers → Archetype B."""
        assert detect_archetype(ARCHETYPE_B_BODY) == "B"

    def test_detects_archetype_a_as_fallback(self):
        """Notes with only date stamps and no other structure → Archetype A."""
        assert detect_archetype(ARCHETYPE_A_BODY) == "A"

    def test_audio_link_overrides_day_markers(self):
        """
        Archetype E detection takes priority over D.
        A travel note with embedded audio recordings should be detected as E.
        """
        body = ARCHETYPE_D_BODY + "\n[recording.m4a](:/abc123)"
        assert detect_archetype(body) == "E"

    def test_day_marker_detection_is_case_insensitive(self):
        """Day names in any case trigger Archetype D detection."""
        assert detect_archetype("monday we went to the market") == "D"

    def test_standalone_day_name_triggers_d(self):
        """A standalone day name on its own line triggers Archetype D."""
        body = "We arrived late.\n\nSunday\n\nWent for a walk."
        assert detect_archetype(body) == "D"


# ============================================================================
# chunk_note() TESTS
# ============================================================================


class TestChunkNote:
    """
    Tests for the public chunk_note() API.

    Threshold behavior and dispatch to correct archetype chunker are tested.
    Actual chunk content is validated against placeholder output shape.
    """

    def test_returns_empty_list_below_threshold(self):
        """Notes shorter than threshold return no chunks."""
        result = chunk_note(SHORT_BODY, created_at=CREATED_AT)
        assert result == []

    def test_returns_empty_list_exactly_at_threshold_minus_one(self):
        """Notes at exactly threshold - 1 characters return no chunks."""
        body = "x" * 999
        assert chunk_note(body, created_at=CREATED_AT) == []

    def test_returns_chunks_at_threshold(self):
        """Notes at exactly the threshold character count are chunked."""
        body = "x" * 1000
        result = chunk_note(body, created_at=CREATED_AT)
        assert len(result) > 0

    def test_returns_list_of_chunk_objects(self):
        """chunk_note returns a list of Chunk instances."""
        result = chunk_note(ARCHETYPE_A_BODY * 10, created_at=CREATED_AT)
        assert all(isinstance(c, Chunk) for c in result)

    def test_chunk_fields_are_present(self):
        """Every returned chunk has all required fields populated."""
        result = chunk_note(ARCHETYPE_B_BODY * 5, created_at=CREATED_AT)
        for chunk in result:
            assert isinstance(chunk.chunk_index, int)
            assert isinstance(chunk.chunk_text, str)
            assert isinstance(chunk.char_start, int)
            assert isinstance(chunk.char_end, int)
            assert isinstance(chunk.resource_ids, list)
            assert isinstance(chunk.metadata, dict)

    def test_dispatches_to_archetype_d_for_travel_note(self):
        """Travel note body dispatches to Archetype D chunker."""
        result = chunk_note(ARCHETYPE_D_BODY * 3, created_at=CREATED_AT)
        assert result[0].metadata.get("archetype") == "D"

    def test_dispatches_to_archetype_e_for_audio_note(self):
        """Note with audio links dispatches to Archetype E chunker."""
        result = chunk_note(ARCHETYPE_E_BODY * 3, created_at=CREATED_AT)
        assert result[0].metadata.get("archetype") == "E"

    def test_title_hint_influences_dispatch(self):
        """Title hint 'Ireland' causes dispatch to Archetype D."""
        body = "We had a great time. " * 60
        result = chunk_note(body, created_at=CREATED_AT, title="Ireland 2021")
        assert result[0].metadata.get("archetype") == "D"

    def test_notebook_hint_influences_dispatch(self):
        """Notebook hint 'Travel' causes dispatch to Archetype D."""
        body = "We had a great time. " * 60
        result = chunk_note(body, created_at=CREATED_AT, notebook="Travel")
        assert result[0].metadata.get("archetype") == "D"


# ============================================================================
# CHUNK DATACLASS TESTS
# ============================================================================


class TestChunk:
    """
    Tests for the Chunk dataclass.

    Validates default values and field types.
    """

    def test_required_fields(self):
        """Chunk can be constructed with only required fields."""
        chunk = Chunk(
            chunk_index=0,
            chunk_text="Hello world",
            char_start=0,
            char_end=11,
        )
        assert chunk.chunk_index == 0
        assert chunk.chunk_text == "Hello world"
        assert chunk.char_start == 0
        assert chunk.char_end == 11

    def test_optional_fields_default_to_none_or_empty(self):
        """Optional fields default correctly without explicit values."""
        chunk = Chunk(chunk_index=0, chunk_text="x", char_start=0, char_end=1)
        assert chunk.section_title is None
        assert chunk.entry_timestamp is None
        assert chunk.resource_ids == []
        assert chunk.metadata == {}

    def test_resource_ids_are_independent_per_instance(self):
        """
        resource_ids list is not shared between instances.
        Validates that dataclass field(default_factory=list) is working correctly.
        """
        chunk_a = Chunk(chunk_index=0, chunk_text="a", char_start=0, char_end=1)
        chunk_b = Chunk(chunk_index=1, chunk_text="b", char_start=1, char_end=2)
        chunk_a.resource_ids.append("abc123")
        assert chunk_b.resource_ids == []
