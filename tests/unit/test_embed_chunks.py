"""
tests/unit/test_embed_chunks.py

Unit tests for pke/cli/embed_chunks.py

═══════════════════════════════════════════════════════════════════
WHAT THIS FILE TESTS
═══════════════════════════════════════════════════════════════════

embed_chunks.py is a standalone CLI command that walks all chunks
where embedding IS NULL and generates embeddings via the OpenAI API.
It is designed to be run independently of ingestion — either as a
one-time backfill or after any ingest that adds new chunks.

This file tests:
    - Core behaviour: fetch → generate → update pipeline
    - Batching: processes chunks in batches of 100, stops correctly
    - Idempotency: only processes chunks without embeddings
    - Progress logging: start, progress, and done messages
    - Environment wiring: credentials passed to the right constructors

═══════════════════════════════════════════════════════════════════
WHY EVERYTHING IS MOCKED
═══════════════════════════════════════════════════════════════════

embed_chunks.py has three external dependencies:
    1. create_client (Supabase)      — connects to a live database
    2. SupabaseClient                — wraps the Supabase connection
    3. OpenAIEmbeddingClient         — calls the OpenAI API

All three are constructed inside the embed_chunks() function using
environment variables read at call time. To test without real
credentials or network calls, we patch all three at the module level
using unittest.mock.patch.

The pattern used throughout this file:

    with patch("pke.cli.embed_chunks.create_client"), \\
         patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \\
         patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
        embed_chunks()

This replaces the real constructors with mocks for the duration of
the test, then restores them automatically when the with block exits.

═══════════════════════════════════════════════════════════════════
IDEMPOTENCY — THE CORE DESIGN GUARANTEE
═══════════════════════════════════════════════════════════════════

embed_chunks.py is designed to be safe to re-run at any time.
The idempotency guarantee works at the database level:

    fetch_unembedded_chunks() returns only chunks WHERE embedding IS NULL

This means:
    - Running embed_chunks twice does not double-embed anything
    - A partial run (interrupted mid-batch) can be safely resumed
    - Re-ingesting notes (which deletes and recreates chunks) leaves
      those chunks with NULL embeddings, triggering re-embedding
      on the next run

The CLI itself does no additional filtering — it trusts the database
contract. Tests here verify that the CLI processes every chunk
returned by fetch_unembedded_chunks() and does not skip any.

═══════════════════════════════════════════════════════════════════
TEST STRUCTURE
═══════════════════════════════════════════════════════════════════

    TestEmbedChunksCore     — fundamental fetch → generate → update flow
    TestBatching            — batch size, multiple batches, loop termination
    TestProgressLogging     — start, progress every 50, done with total
    TestEnvironmentWiring   — credentials reach the right constructors
"""

import logging
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS AND HELPERS
# ═══════════════════════════════════════════════════════════════════

# Fixed embedding vector used as the return value for all generate() calls.
# 1536 dimensions matches OpenAI text-embedding-3-small output.
FAKE_EMBEDDING = [0.1] * 1536

# Realistic environment variables injected via monkeypatch.
# These are never sent to real services — the constructors are mocked.
ENV_VARS = {
    "OPENAI_API_KEY": "test-openai-key",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_KEY": "test-supabase-key",
}


def make_chunk(chunk_id, text="Some chunk text"):
    """
    Build a dict simulating a row returned by fetch_unembedded_chunks().

    The CLI reads two fields from each chunk:
        id         — passed to update_chunk_embedding() to identify the row
        chunk_text — passed to generate() to produce the embedding

    Any other fields in the real schema are ignored by the CLI.
    """
    return {"id": chunk_id, "chunk_text": text}


def make_clients(chunks_by_batch):
    """
    Build a pair of mocked clients with a pre-programmed batch sequence.

    chunks_by_batch is a list of lists — each inner list represents
    one call to fetch_unembedded_chunks(). After all batches are
    exhausted, an empty list is returned to signal completion.

    Example:
        make_clients([[chunk1, chunk2], [chunk3]])
        → first call returns [chunk1, chunk2]
        → second call returns [chunk3]
        → third call returns []  (loop exits)

    Parameters
    ----------
    chunks_by_batch : list[list[dict]] — batches to return in sequence

    Returns
    -------
    (supabase_mock, embedder_mock)
    """
    supabase = MagicMock()
    # side_effect takes a list — each call pops the next value
    supabase.fetch_unembedded_chunks.side_effect = chunks_by_batch + [[]]

    embedder = MagicMock()
    embedder.generate.return_value = FAKE_EMBEDDING

    return supabase, embedder


# ═══════════════════════════════════════════════════════════════════
# TEST CLASSES
# ═══════════════════════════════════════════════════════════════════

class TestEmbedChunksCore:
    """
    Verify the fundamental fetch → generate → update pipeline.

    This is the core contract of embed_chunks.py:
        For every chunk returned by fetch_unembedded_chunks():
            1. Call generate(chunk_text) to produce an embedding
            2. Call update_chunk_embedding(chunk_id, embedding)

    The tests here verify this contract holds for zero chunks,
    one chunk, and multiple chunks — and that the operations
    are performed in the correct order.
    """

    def test_exits_cleanly_when_no_chunks(self, monkeypatch):
        """
        When fetch_unembedded_chunks returns [] immediately, the CLI
        must exit without calling generate() or update_chunk_embedding().

        This is the "already done" case — safe to run when all chunks
        are already embedded.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        supabase = MagicMock()
        supabase.fetch_unembedded_chunks.return_value = []
        embedder = MagicMock()

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        embedder.generate.assert_not_called()
        supabase.update_chunk_embedding.assert_not_called()

    def test_single_batch_embeds_all_chunks(self, monkeypatch):
        """
        Every chunk in a batch must be embedded. generate() and
        update_chunk_embedding() must each be called once per chunk.
        No chunk should be silently skipped.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        chunks = [make_chunk(f"id-{i}") for i in range(3)]
        supabase, embedder = make_clients([chunks])

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        assert embedder.generate.call_count == 3
        assert supabase.update_chunk_embedding.call_count == 3

    def test_generate_called_with_chunk_text(self, monkeypatch):
        """
        generate() must receive the chunk_text field, not the chunk id
        or the whole dict. Passing the wrong value would embed
        meaningless content.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        chunks = [make_chunk("id-1", text="My specific chunk text")]
        supabase, embedder = make_clients([chunks])

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        embedder.generate.assert_called_with("My specific chunk text")

    def test_update_called_with_chunk_id_and_embedding(self, monkeypatch):
        """
        update_chunk_embedding() must receive the chunk's id and the
        embedding vector produced by generate(). The id identifies
        which row to update; the vector is what gets stored.

        If the id is wrong, the wrong chunk row gets the embedding.
        If the vector is wrong, the stored embedding is incorrect.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        chunks = [make_chunk("chunk-uuid-99")]
        supabase, embedder = make_clients([chunks])

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        supabase.update_chunk_embedding.assert_called_once_with(
            "chunk-uuid-99", FAKE_EMBEDDING
        )

    def test_generate_called_before_update_for_each_chunk(self, monkeypatch):
        """
        For each chunk, generate() must be called before update().
        Calling update() before generate() would store a stale or
        default vector rather than the freshly computed embedding.

        This test tracks the call order using side_effect functions
        that append to a shared list.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        call_order = []
        chunks = [make_chunk("id-1", text="text")]
        supabase = MagicMock()
        supabase.fetch_unembedded_chunks.side_effect = [chunks, []]
        embedder = MagicMock()

        def track_generate(text):
            call_order.append("generate")
            return FAKE_EMBEDDING

        def track_update(chunk_id, embedding):
            call_order.append("update")

        embedder.generate.side_effect = track_generate
        supabase.update_chunk_embedding.side_effect = track_update

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        assert call_order == ["generate", "update"]


class TestBatching:
    """
    Verify the batch processing loop behaves correctly.

    WHY BATCHING MATTERS:
        The corpus has 866+ chunks and will grow. Fetching all chunks
        into memory at once would be expensive and fragile. Batches
        of 100 keep memory usage flat regardless of total chunk count.

        The loop must:
            - Always fetch with batch_size=100
            - Process each batch completely before fetching the next
            - Stop when fetch returns an empty list
            - Handle multiple batches correctly across a full run
    """

    def test_fetch_called_with_batch_size_100(self, monkeypatch):
        """
        batch_size=100 is the hardcoded batch size. This test verifies
        it is passed correctly to fetch_unembedded_chunks(). A wrong
        batch size would either over-fetch (memory pressure) or
        under-fetch (slower processing).
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        supabase = MagicMock()
        supabase.fetch_unembedded_chunks.return_value = []
        embedder = MagicMock()

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        supabase.fetch_unembedded_chunks.assert_called_with(batch_size=100)

    def test_multiple_batches_all_chunks_embedded(self, monkeypatch):
        """
        When chunks span multiple batches, all chunks must be embedded.
        The total call count across all batches must equal the total
        number of chunks — no batch should be silently skipped.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        batch1 = [make_chunk(f"b1-{i}") for i in range(3)]
        batch2 = [make_chunk(f"b2-{i}") for i in range(2)]
        supabase, embedder = make_clients([batch1, batch2])

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        # 3 from batch1 + 2 from batch2 = 5 total
        assert embedder.generate.call_count == 5
        assert supabase.update_chunk_embedding.call_count == 5

    def test_loop_terminates_on_empty_batch(self, monkeypatch):
        """
        The while loop must exit when fetch_unembedded_chunks returns [].
        An infinite loop here would hang the process indefinitely.

        make_clients appends [] automatically after all batches.
        This test verifies the loop fetches exactly twice:
            call 1: returns batch1 (processed)
            call 2: returns []    (loop exits)
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        batch1 = [make_chunk("id-1")]
        supabase, embedder = make_clients([batch1])

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        assert supabase.fetch_unembedded_chunks.call_count == 2

    def test_idempotency_all_returned_chunks_are_processed(self, monkeypatch):
        """
        Idempotency is enforced by the database contract:
        fetch_unembedded_chunks() only returns chunks WHERE embedding IS NULL.

        The CLI trusts this contract completely — it processes every
        chunk returned without additional filtering. This test verifies
        that no returned chunk is silently skipped by the CLI.

        If the CLI added its own filtering logic, it would create a
        mismatch between what the database offers and what gets embedded,
        breaking the idempotency guarantee.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        chunks = [make_chunk("id-1"), make_chunk("id-2")]
        supabase, embedder = make_clients([chunks])

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        assert supabase.update_chunk_embedding.call_count == 2


class TestProgressLogging:
    """
    Verify that progress is logged correctly during a run.

    WHY LOGGING MATTERS HERE:
        embed_chunks.py is a long-running CLI command. During the
        initial 866-chunk backfill it may run for several minutes.
        Without progress logging, there is no way to tell whether
        the process is running, stalled, or nearly done.

        The logging contract:
            - "Starting..." message at the beginning of every run
            - "Embedded N chunks..." progress message every 50 chunks
            - "Done. N chunks embedded." message at completion

        These tests use pytest's caplog fixture to capture log records
        and verify the messages are emitted at the correct points.
    """

    def test_start_message_logged(self, monkeypatch, caplog):
        """
        A "Starting..." message must be logged before any processing
        begins. This confirms the process is running and gives a
        clear starting point in the log output.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        supabase = MagicMock()
        supabase.fetch_unembedded_chunks.return_value = []
        embedder = MagicMock()

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase), \
             caplog.at_level(logging.INFO, logger="pke.embed_chunks"):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        assert any("Starting" in r.message for r in caplog.records)

    def test_done_message_logged_with_total_count(self, monkeypatch, caplog):
        """
        A "Done. N chunks embedded." message must be logged at
        completion with the exact total count. This is the primary
        confirmation that a run completed successfully and tells
        the operator how many chunks were processed.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        chunks = [make_chunk(f"id-{i}") for i in range(3)]
        supabase, embedder = make_clients([chunks])

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase), \
             caplog.at_level(logging.INFO, logger="pke.embed_chunks"):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        assert any("3" in r.message and "Done" in r.message for r in caplog.records)

    def test_progress_logged_at_50_chunk_boundary(self, monkeypatch, caplog):
        """
        A progress message must be emitted after every 50th chunk.
        This gives live feedback during long runs.

        With exactly 50 chunks: one progress message at chunk 50.
        The implementation uses: if total % 50 == 0: log progress
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        chunks = [make_chunk(f"id-{i}") for i in range(50)]
        supabase, embedder = make_clients([chunks])

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase), \
             caplog.at_level(logging.INFO, logger="pke.embed_chunks"):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        progress_logs = [
            r for r in caplog.records
            if "Embedded" in r.message and "chunks" in r.message
        ]
        assert len(progress_logs) == 1
        assert "50" in progress_logs[0].message

    def test_no_progress_log_below_50_chunks(self, monkeypatch, caplog):
        """
        No progress message should be emitted for fewer than 50 chunks.
        With 49 chunks: 49 % 50 == 49, never reaching the boundary.
        The "Done" message still appears — that is separate.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        chunks = [make_chunk(f"id-{i}") for i in range(49)]
        supabase, embedder = make_clients([chunks])

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase), \
             caplog.at_level(logging.INFO, logger="pke.embed_chunks"):
            from pke.cli.embed_chunks import embed_chunks
            embed_chunks()

        progress_logs = [
            r for r in caplog.records
            if "Embedded" in r.message and "chunks" in r.message
        ]
        assert len(progress_logs) == 0


class TestEnvironmentWiring:
    """
    Verify that environment variables are passed to the correct
    constructors.

    WHY THIS MATTERS:
        embed_chunks.py reads credentials from environment variables
        and passes them to client constructors. If the wrong variable
        is passed to the wrong constructor:
            - OpenAI calls fail with an auth error
            - Supabase calls fail with a connection error

        These failures would be silent in normal test runs because
        the clients are mocked. This class explicitly verifies the
        wiring — that the right credential reaches the right place.

        This is also a lightweight form of configuration contract
        testing — verifying that the CLI honours the documented
        environment variable names (OPENAI_API_KEY, SUPABASE_URL,
        SUPABASE_KEY).
    """

    def test_openai_api_key_passed_to_embedding_client(self, monkeypatch):
        """
        OPENAI_API_KEY must be passed as the api_key parameter to
        OpenAIEmbeddingClient. The wrong key would cause all embedding
        calls to fail with an authentication error.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        supabase = MagicMock()
        supabase.fetch_unembedded_chunks.return_value = []

        with patch("pke.cli.embed_chunks.create_client"), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            with patch("pke.cli.embed_chunks.OpenAIEmbeddingClient") as mock_cls:
                mock_cls.return_value.generate.return_value = FAKE_EMBEDDING
                from pke.cli.embed_chunks import embed_chunks
                embed_chunks()
            mock_cls.assert_called_once_with(api_key="test-openai-key")

    def test_supabase_url_and_key_passed_to_create_client(self, monkeypatch):
        """
        SUPABASE_URL and SUPABASE_KEY must be passed to create_client()
        in the correct positional order. The wrong URL would cause a
        connection failure; the wrong key would cause an auth failure.
        """
        monkeypatch.setattr("os.environ", ENV_VARS)
        supabase = MagicMock()
        supabase.fetch_unembedded_chunks.return_value = []
        embedder = MagicMock()
        embedder.generate.return_value = FAKE_EMBEDDING

        with patch("pke.cli.embed_chunks.OpenAIEmbeddingClient", return_value=embedder), \
             patch("pke.cli.embed_chunks.SupabaseClient", return_value=supabase):
            with patch("pke.cli.embed_chunks.create_client") as mock_create:
                mock_create.return_value = MagicMock()
                from pke.cli.embed_chunks import embed_chunks
                embed_chunks()
            mock_create.assert_called_once_with(
                "https://test.supabase.co",
                "test-supabase-key",
            )
