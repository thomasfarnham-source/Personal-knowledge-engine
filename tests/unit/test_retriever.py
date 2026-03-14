"""
tests/unit/test_retriever.py

Unit tests for pke/retrieval/retriever.py

═══════════════════════════════════════════════════════════════════
WHAT THIS FILE TESTS
═══════════════════════════════════════════════════════════════════

The Retriever class is the core intelligence of the PKE query system.
It takes a plain text query, embeds it, searches two database tables,
merges and ranks the results, and returns a clean list of QueryResult
objects to the API layer.

This file tests that logic in complete isolation — no real database,
no real OpenAI API, no network calls of any kind.

═══════════════════════════════════════════════════════════════════
WHY UNIT TESTS (NOT INTEGRATION TESTS) FOR THE RETRIEVER
═══════════════════════════════════════════════════════════════════

The Retriever has two external dependencies:
    1. SupabaseClient          — talks to a real Postgres database
    2. OpenAIEmbeddingClient   — talks to the OpenAI API

Both are injected as constructor parameters (dependency injection).
This is deliberate architectural design — it makes the Retriever
independently testable without needing live services.

In these tests, both dependencies are replaced with MagicMock objects
that return controlled, predictable data. This means:
    - Tests run in milliseconds (no network latency)
    - Tests are deterministic (no flaky external responses)
    - Tests can simulate edge cases that are hard to reproduce
      against a real database (empty results, specific score values)
    - Tests document exactly what the Retriever expects from its
      dependencies — a form of implicit contract documentation

═══════════════════════════════════════════════════════════════════
WHAT A MOCK IS
═══════════════════════════════════════════════════════════════════

A MagicMock is a stand-in object that:
    - Accepts any method call without raising an error
    - Returns configurable values when those methods are called
    - Records every call made to it so tests can verify behaviour

Example:
    mock = MagicMock()
    mock.generate.return_value = [0.1, 0.2, 0.3]
    result = mock.generate("some text")   # returns [0.1, 0.2, 0.3]
    mock.generate.assert_called_once_with("some text")  # passes

The mock doesn't know anything about OpenAI. It just pretends to be
an embedding client and returns whatever we tell it to return.

═══════════════════════════════════════════════════════════════════
TEST STRUCTURE
═══════════════════════════════════════════════════════════════════

Tests are grouped into classes by concern:

    TestRetrieverConstruction   — default and custom parameter values
    TestQueryEmbedding          — query text is embedded before search
    TestSupabaseCalls           — correct parameters passed to RPCs
    TestChunkResultConstruction — chunk rows mapped to QueryResult correctly
    TestNoteResultConstruction  — note rows mapped to QueryResult correctly
    TestRankingAndLimit         — results sorted and capped correctly
    TestScoreHook               — _score() isolated and correct

Each class tests one concern. If a test fails, the class name tells
you immediately which part of the Retriever is broken.
"""

from unittest.mock import MagicMock

from pke.retrieval.retriever import Retriever

# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

# A realistic embedding vector — 1536 dimensions of 0.1.
# This matches the OpenAI text-embedding-3-small output dimensions.
# Using a fixed value makes assertions predictable.
FAKE_EMBEDDING = [0.1] * 1536


# ═══════════════════════════════════════════════════════════════════
# HELPER FACTORIES
# ═══════════════════════════════════════════════════════════════════
#
# These factory functions create mock objects and test data with
# sensible defaults. Tests override only the fields they care about.
# This keeps test code concise and focused on what is being tested.


def make_supabase_mock(chunk_rows=None, note_rows=None):
    """
    Build a mock SupabaseClient with configurable RPC return values.

    match_chunks and match_notes are the two RPC methods the Retriever
    calls. By controlling their return values here, we control exactly
    what the Retriever has to work with in each test.

    Parameters
    ----------
    chunk_rows : list of dicts simulating rows from the chunks table
    note_rows  : list of dicts simulating rows from the notes table
    """
    mock = MagicMock()
    mock.match_chunks.return_value = chunk_rows or []
    mock.match_notes.return_value = note_rows or []
    return mock


def make_embedding_mock(embedding=None):
    """
    Build a mock OpenAIEmbeddingClient that returns a fixed vector.

    The generate() method is the only method the Retriever calls on
    the embedding client. We return FAKE_EMBEDDING by default, or a
    custom vector when a test needs to verify that a specific vector
    was passed downstream to the Supabase RPCs.
    """
    mock = MagicMock()
    mock.generate.return_value = embedding or FAKE_EMBEDDING
    return mock


def make_chunk_row(
    note_id="note-uuid-1",
    note_title="Ireland 2019",
    notebook="Travel",
    chunk_text="We arrived in Dublin on a grey morning.",
    similarity=0.82,
    chunk_index=2,
    section_title="Day 1",
    entry_timestamp="2019-06-01",
    resource_ids=None,
):
    """
    Build a dict simulating a row returned by the match_chunks RPC.

    This is the shape of data the Retriever receives from Supabase
    after a pgvector similarity search on the chunks table. The
    Retriever must map this dict faithfully into a QueryResult object.

    Fields:
        note_id         — UUID of the parent note (as string from DB)
        note_title      — resolved note title (joined at DB level)
        notebook        — resolved notebook name (joined at DB level)
        chunk_text      — the actual text passage to surface in the panel
        similarity      — cosine similarity score from pgvector (<=>)
        chunk_index     — position of this chunk within the parent note
        section_title   — detected section heading, if any
        entry_timestamp — explicit or calculated date, or None
        resource_ids    — list of Joplin resource IDs (images, audio)
    """
    return {
        "note_id": note_id,
        "note_title": note_title,
        "notebook": notebook,
        "chunk_text": chunk_text,
        "similarity": similarity,
        "chunk_index": chunk_index,
        "section_title": section_title,
        "entry_timestamp": entry_timestamp,
        "resource_ids": resource_ids or [],
    }


def make_note_row(
    note_id="note-uuid-2",
    note_title="Miscellaneous thoughts",
    notebook="Journal",
    note_text="A short note with no chunks.",
    similarity=0.55,
):
    """
    Build a dict simulating a row returned by the match_notes RPC.

    This is the fallback search path — notes below the chunking
    threshold that have no chunk-level embeddings. The match_notes
    RPC uses a NOT EXISTS subquery to ensure these results never
    overlap with chunk results.

    Fields:
        note_id    — UUID of the note
        note_title — note title
        notebook   — notebook name
        note_text  — full note body (used as matched_text in result)
        similarity — cosine similarity score
    """
    return {
        "note_id": note_id,
        "note_title": note_title,
        "notebook": notebook,
        "note_text": note_text,
        "similarity": similarity,
    }


# ═══════════════════════════════════════════════════════════════════
# TEST CLASSES
# ═══════════════════════════════════════════════════════════════════


class TestRetrieverConstruction:
    """
    Verify that the Retriever initialises with correct default values
    and accepts custom limit overrides.

    WHY THIS MATTERS:
        chunk_limit and note_limit control how many candidates are
        fetched from each table before re-ranking. If these defaults
        are wrong, retrieval quality degrades silently — the system
        still works but surfaces fewer candidates than it should.
    """

    def test_default_limits(self):
        """chunk_limit=10 and note_limit=5 are the baseline candidates."""
        retriever = Retriever(
            supabase_client=make_supabase_mock(),
            embedding_client=make_embedding_mock(),
        )
        assert retriever.chunk_limit == 10
        assert retriever.note_limit == 5

    def test_custom_limits(self):
        """Limits can be overridden at construction time for tuning."""
        retriever = Retriever(
            supabase_client=make_supabase_mock(),
            embedding_client=make_embedding_mock(),
            chunk_limit=20,
            note_limit=10,
        )
        assert retriever.chunk_limit == 20
        assert retriever.note_limit == 10


class TestQueryEmbedding:
    """
    Verify that the query text is embedded before being passed to
    the Supabase RPCs, and that the correct vector is forwarded.

    WHY THIS MATTERS:
        The entire retrieval system depends on the query being embedded
        with the same model used to embed notes and chunks at ingest
        time (text-embedding-3-small). If the wrong text is embedded,
        or the embedding is not forwarded correctly, the similarity
        scores will be meaningless.

        This is step 1 of the hybrid retrieval pipeline. Everything
        downstream depends on it being correct.
    """

    def test_embedding_called_with_query_text(self):
        """
        The exact query string from the caller must be passed to
        generate(). Any silent transformation (trimming, lowercasing)
        would alter retrieval behaviour without warning.
        """
        embedder = make_embedding_mock()
        retriever = Retriever(
            supabase_client=make_supabase_mock(),
            embedding_client=embedder,
        )
        retriever.query("Ireland family history")
        embedder.generate.assert_called_once_with("Ireland family history")

    def test_embedding_vector_passed_to_match_chunks(self):
        """
        The vector returned by generate() must reach match_chunks
        unchanged. If the wrong vector reaches the RPC, the pgvector
        distance calculation is silently wrong.
        """
        custom_embedding = [0.5] * 1536
        embedder = make_embedding_mock(embedding=custom_embedding)
        supabase = make_supabase_mock()
        retriever = Retriever(supabase_client=supabase, embedding_client=embedder)
        retriever.query("test query")
        assert supabase.match_chunks.call_args.kwargs["query_embedding"] == custom_embedding

    def test_embedding_vector_passed_to_match_notes(self):
        """
        The same vector must reach match_notes. Both RPCs must search
        the same vector space for merged results to be comparable.
        """
        custom_embedding = [0.5] * 1536
        embedder = make_embedding_mock(embedding=custom_embedding)
        supabase = make_supabase_mock()
        retriever = Retriever(supabase_client=supabase, embedding_client=embedder)
        retriever.query("test query")
        assert supabase.match_notes.call_args.kwargs["query_embedding"] == custom_embedding


class TestSupabaseCalls:
    """
    Verify that correct parameters are passed to both Supabase RPCs
    for every query configuration.

    WHY THIS MATTERS:
        The Retriever passes three parameters to each RPC:
            query_embedding  — the search vector
            match_count      — how many candidates to return
            filter_notebook  — optional scoping filter

        If any of these are wrong, the RPC either returns wrong
        results silently or ignores the user's filter. These tests
        verify the wiring between the Retriever's public API and
        the underlying RPCs.
    """

    def test_match_chunks_called_with_correct_limit(self):
        """
        chunk_limit is passed as match_count to match_chunks.
        Controls how many chunk candidates are fetched before
        the final re-ranking step.
        """
        supabase = make_supabase_mock()
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
            chunk_limit=15,
        )
        retriever.query("test")
        assert supabase.match_chunks.call_args.kwargs["match_count"] == 15

    def test_match_notes_called_with_correct_limit(self):
        """
        note_limit is passed as match_count to match_notes.
        The note fallback pool is intentionally smaller than the
        chunk pool — notes below the chunking threshold are shorter
        and less semantically dense.
        """
        supabase = make_supabase_mock()
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
            note_limit=8,
        )
        retriever.query("test")
        assert supabase.match_notes.call_args.kwargs["match_count"] == 8

    def test_notebook_filter_passed_to_both_rpcs(self):
        """
        When the caller specifies a notebook filter, it must reach
        BOTH RPCs. Forwarding to only one would produce inconsistent
        results — filtered chunks mixed with unfiltered note fallbacks.
        """
        supabase = make_supabase_mock()
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        retriever.query("test", notebook="Travel")
        assert supabase.match_chunks.call_args.kwargs["filter_notebook"] == "Travel"
        assert supabase.match_notes.call_args.kwargs["filter_notebook"] == "Travel"

    def test_notebook_none_by_default(self):
        """
        When no notebook is specified, None is passed to both RPCs.
        The RPC implementations interpret None as "search all notebooks."
        """
        supabase = make_supabase_mock()
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        retriever.query("test")
        assert supabase.match_chunks.call_args.kwargs["filter_notebook"] is None
        assert supabase.match_notes.call_args.kwargs["filter_notebook"] is None


class TestChunkResultConstruction:
    """
    Verify that chunk rows from Supabase are mapped faithfully and
    completely into QueryResult objects.

    WHY THIS MATTERS:
        The QueryResult is the contract between the Retriever and the
        Obsidian insight panel. Every field has a specific purpose:

            note_id         → deep link back to the source note
            note_title      → human-readable label in the panel
            notebook        → context and filtering display
            matched_text    → the passage surfaced to the user
            similarity_score → used for internal ranking (not shown)
            chunk_index     → navigation to exact paragraph
            section_title   → section context in the panel
            entry_timestamp → temporal context ("when was this written")
            resource_ids    → images and audio linked from this chunk
            result_type     → "chunk" distinguishes from note fallbacks

        If any field is mapped incorrectly, the UI shows wrong data
        or breaks navigation. These tests verify every field.
    """

    def test_chunk_result_fields(self):
        """
        Every field in the chunk row must be mapped to the correct
        field in the QueryResult. No field should be silently dropped
        or mapped to the wrong attribute.
        """
        row = make_chunk_row()
        supabase = make_supabase_mock(chunk_rows=[row])
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test")
        assert len(results) == 1
        r = results[0]
        assert r.note_id == "note-uuid-1"
        assert r.note_title == "Ireland 2019"
        assert r.notebook == "Travel"
        assert r.matched_text == "We arrived in Dublin on a grey morning."
        assert r.similarity_score == 0.82
        assert r.chunk_index == 2
        assert r.section_title == "Day 1"
        assert r.entry_timestamp == "2019-06-01"
        assert r.resource_ids == []
        assert r.result_type == "chunk"

    def test_chunk_result_with_resource_ids(self):
        """
        resource_ids carries Joplin resource IDs for images and audio.
        Used by the Obsidian plugin to render inline media and audio
        play buttons. Must pass through intact.
        """
        row = make_chunk_row(resource_ids=["abc123", "def456"])
        supabase = make_supabase_mock(chunk_rows=[row])
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test")
        assert results[0].resource_ids == ["abc123", "def456"]

    def test_chunk_result_none_resource_ids_normalised_to_empty_list(self):
        """
        The DB may return NULL for resource_ids on chunks with no
        media. The Retriever normalises this to [] rather than passing
        None to the QueryResult — which would break the plugin when
        it tries to iterate the list.

        This is an explicit defensive mapping in the Retriever:
            resource_ids=row.get("resource_ids") or []
        """
        row = make_chunk_row(resource_ids=None)
        supabase = make_supabase_mock(chunk_rows=[row])
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test")
        assert results[0].resource_ids == []

    def test_chunk_result_optional_fields_can_be_none(self):
        """
        section_title, entry_timestamp, and chunk_index are all
        optional — not every chunk has a detected section, a
        recoverable timestamp, or a meaningful index. The Retriever
        must pass None through cleanly without raising or substituting
        a misleading default.
        """
        row = make_chunk_row(
            section_title=None,
            entry_timestamp=None,
            chunk_index=None,
        )
        supabase = make_supabase_mock(chunk_rows=[row])
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test")
        r = results[0]
        assert r.section_title is None
        assert r.entry_timestamp is None
        assert r.chunk_index is None


class TestNoteResultConstruction:
    """
    Verify that note rows from the fallback search are mapped
    correctly into QueryResult objects.

    WHY THIS MATTERS:
        Note-level results come from a different RPC (match_notes)
        and have a different row shape than chunk results. Key
        differences:
            - matched_text comes from note_text (not chunk_text)
            - result_type must be "note" (not "chunk")
            - chunk-specific fields are absent from the row and
              must default to None / []

        These notes are below the chunking threshold — shorter,
        less structured notes where whole-note embedding is
        sufficient. They are a legitimate part of the corpus.
    """

    def test_note_result_fields(self):
        """
        Core fields must be mapped from the note row correctly.
        matched_text comes from note_text — the key difference
        from chunk result construction.
        """
        row = make_note_row()
        supabase = make_supabase_mock(note_rows=[row])
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test")
        assert len(results) == 1
        r = results[0]
        assert r.note_id == "note-uuid-2"
        assert r.note_title == "Miscellaneous thoughts"
        assert r.notebook == "Journal"
        assert r.matched_text == "A short note with no chunks."
        assert r.similarity_score == 0.55
        assert r.result_type == "note"

    def test_note_result_optional_fields_default_to_none(self):
        """
        Note rows do not carry chunk-specific fields. The Retriever
        constructs QueryResult without passing these — Pydantic
        defaults apply (None for Optional, [] for List fields).

        The Obsidian plugin must handle None gracefully for these
        fields on note-type results.
        """
        row = make_note_row()
        supabase = make_supabase_mock(note_rows=[row])
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test")
        r = results[0]
        assert r.chunk_index is None
        assert r.section_title is None
        assert r.entry_timestamp is None
        assert r.resource_ids == []


class TestRankingAndLimit:
    """
    Verify that the merged result list is sorted by similarity score
    descending, and that the final limit is applied after merging.

    WHY THIS MATTERS:
        The hybrid strategy fetches up to chunk_limit + note_limit
        candidates total. These are merged into a single list and
        re-ranked. The caller's limit is applied AFTER this merge.

        This means:
            - A high-scoring note result can outrank a low-scoring
              chunk result — result_type does not determine order
            - The final list always contains the best results across
              both tables, not an arbitrary split between them
            - The caller receives exactly limit results (or fewer
              if fewer candidates exist)

        If ranking or limit logic is wrong, the insight panel shows
        the wrong passages — lower-quality results surfaced over
        higher-quality ones.
    """

    def test_results_sorted_by_similarity_descending(self):
        """
        Results must be ranked highest-to-lowest regardless of the
        order returned by the RPCs. The pgvector RPC may return
        results in any order — the Retriever owns final ranking.
        """
        rows = [
            make_chunk_row(note_id="a", similarity=0.60),
            make_chunk_row(note_id="b", similarity=0.90),
            make_chunk_row(note_id="c", similarity=0.75),
        ]
        supabase = make_supabase_mock(chunk_rows=rows)
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test", limit=3)
        scores = [r.similarity_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_limit_applied_after_merge(self):
        """
        The limit applies to the merged chunk + note list, not to
        each source separately. This is what makes the hybrid
        strategy coherent — the best N results across both tables.
        """
        chunk_rows = [make_chunk_row(note_id=f"c{i}", similarity=0.5 + i * 0.01) for i in range(8)]
        note_rows = [make_note_row(note_id=f"n{i}") for i in range(3)]
        supabase = make_supabase_mock(chunk_rows=chunk_rows, note_rows=note_rows)
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test", limit=5)
        assert len(results) == 5

    def test_chunk_results_ranked_above_lower_scoring_note_results(self):
        """
        A chunk with similarity 0.80 should rank above a note with
        similarity 0.55 — because of the score, not the type.
        result_type plays no role in ranking.
        """
        chunk_row = make_chunk_row(note_id="chunk-1", similarity=0.80)
        note_row = make_note_row(note_id="note-1", similarity=0.55)
        supabase = make_supabase_mock(chunk_rows=[chunk_row], note_rows=[note_row])
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test", limit=2)
        assert results[0].note_id == "chunk-1"
        assert results[1].note_id == "note-1"

    def test_note_result_ranked_above_lower_scoring_chunk_result(self):
        """
        A note result with a higher similarity score must rank above
        a chunk result with a lower score. Only similarity_score
        determines order — not result_type.
        """
        chunk_row = make_chunk_row(note_id="chunk-1", similarity=0.40)
        note_row = make_note_row(note_id="note-1", similarity=0.90)
        supabase = make_supabase_mock(chunk_rows=[chunk_row], note_rows=[note_row])
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test", limit=2)
        assert results[0].note_id == "note-1"

    def test_returns_empty_list_when_no_results(self):
        """
        When both RPCs return empty lists the Retriever must return
        [], not raise an error. The API layer handles empty results
        gracefully — this is a valid and expected state.
        """
        supabase = make_supabase_mock(chunk_rows=[], note_rows=[])
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test")
        assert results == []

    def test_limit_larger_than_results_returns_all(self):
        """
        If the caller requests more results than exist, all available
        results are returned. The limit is a ceiling, not a minimum.
        Returning fewer results than requested is correct behaviour.
        """
        rows = [make_chunk_row(note_id="a", similarity=0.8)]
        supabase = make_supabase_mock(chunk_rows=rows)
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test", limit=20)
        assert len(results) == 1


class TestScoreHook:
    """
    Verify the _score() method in isolation.

    WHY THIS IS ITS OWN TEST CLASS:
        _score() is intentionally isolated as a hook for future
        extension. It currently returns raw cosine similarity, but
        will eventually incorporate additional signals:
            - Recency decay (weight recent entries higher)
            - Archetype weighting (oral history vs journal fragments)
            - Timestamp confidence (explicit > calculated > null)

        Testing _score() independently documents the current contract:
        it takes a row dict and returns a float. When the
        implementation is extended, these tests catch regressions
        in the base behaviour.

        The isolation also confirms that query() uses _score() for
        all result scoring — if _score() is bypassed, the hook
        loses its purpose.
    """

    def test_score_returns_similarity_field(self):
        """
        Currently _score() reads the 'similarity' key from the row.
        This is the cosine similarity computed by the pgvector <=>
        operator in the Supabase RPC.
        """
        retriever = Retriever(
            supabase_client=make_supabase_mock(),
            embedding_client=make_embedding_mock(),
        )
        assert retriever._score({"similarity": 0.731}) == 0.731

    def test_score_returns_float(self):
        """
        _score() must return a float regardless of input type.
        Postgres may return integers for exact matches (similarity=1).
        The explicit float() cast in the implementation handles this.
        Without it, downstream comparisons could behave unexpectedly.
        """
        retriever = Retriever(
            supabase_client=make_supabase_mock(),
            embedding_client=make_embedding_mock(),
        )
        assert isinstance(retriever._score({"similarity": 1}), float)

    def test_score_zero(self):
        """
        A similarity of 0.0 is valid (orthogonal vectors).
        _score() must not treat it as falsy or substitute a default.
        """
        retriever = Retriever(
            supabase_client=make_supabase_mock(),
            embedding_client=make_embedding_mock(),
        )
        assert retriever._score({"similarity": 0}) == 0.0

    def test_score_wired_into_query_results(self):
        """
        End-to-end confirmation that _score() is actually used by
        query() to populate similarity_score on QueryResult. Confirms
        the hook is wired in — not just defined but never called.
        """
        row = make_chunk_row(similarity=0.654)
        supabase = make_supabase_mock(chunk_rows=[row])
        retriever = Retriever(
            supabase_client=supabase,
            embedding_client=make_embedding_mock(),
        )
        results = retriever.query("test")
        assert results[0].similarity_score == 0.654
