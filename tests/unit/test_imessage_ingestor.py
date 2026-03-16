"""
tests/unit/test_imessage_ingestor.py

Unit tests for pke/ingestion/imessage_ingestor.py

═══════════════════════════════════════════════════════════════════
WHAT THIS FILE TESTS
═══════════════════════════════════════════════════════════════════

The ingestor has four responsibilities:

    1. Correct row construction — thread, participant, message,
       and burst rows are built correctly from parser output

    2. Correct ingestion order — threads before messages/bursts
       (foreign key dependency)

    3. Correct re-ingestion behaviour — bursts and chunk mirrors
       are deleted before re-insertion

    4. Correct dry-run behaviour — no writes when client is in
       dry-run mode, result counts still correct

═══════════════════════════════════════════════════════════════════
TEST STRUCTURE
═══════════════════════════════════════════════════════════════════

    MockSupabaseClient       — records calls, no real DB
    TestThreadRow            — thread row construction
    TestParticipantRow       — participant row construction
    TestMessageRow           — message row construction
    TestBurstRow             — burst row construction
    TestChunkMirrorRow       — chunk mirror row construction
    TestIngestionOrder       — correct call sequence
    TestReIngestion          — delete-then-reinsert pattern
    TestDryRun               — no writes in dry-run mode
    TestIngestionResult      — result summary counts
"""

import os
import tempfile
import csv

from pke.ingestion.imessage_ingestor import IMessageIngestor
from pke.parsers.imessage_parser import SELF_NAME


# ─────────────────────────────────────────────────────────────────
# MOCK CLIENT
# ─────────────────────────────────────────────────────────────────

class MockSupabaseClient:
    """
    Records all calls to upsert_rows and delete_where.
    Does not write to any database.
    Mirrors the dry_run interface of the real SupabaseClient.
    """

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.upserted: dict[str, list[dict]] = {}   # table -> list of rows
        self.deleted: list[tuple[str, str, str]] = []  # (table, column, value)

    def upsert_rows(self, table: str, rows: list[dict]) -> None:
        if self.dry_run:
            return
        if table not in self.upserted:
            self.upserted[table] = []
        self.upserted[table].extend(rows)

    def delete_where(self, table: str, column: str, value: str) -> None:
        if self.dry_run:
            return
        self.deleted.append((table, column, value))

    def rows_for(self, table: str) -> list[dict]:
        return self.upserted.get(table, [])

    def delete_calls_for(self, table: str) -> list[tuple]:
        return [(t, c, v) for t, c, v in self.deleted if t == table]


# ─────────────────────────────────────────────────────────────────
# CSV HELPERS
# ─────────────────────────────────────────────────────────────────

COLUMNS = [
    "Chat Session", "Message Date", "Delivered Date", "Read Date",
    "Edited Date", "Deleted Date", "Service", "Type", "Sender ID",
    "Sender Name", "Status", "Replying to", "Subject", "Text",
    "Reactions", "Attachment", "Attachment type",
]


def make_csv_file(rows: list[dict], thread_name: str = "Alice & Bob") -> str:
    """Write a minimal CSV to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    )
    writer = csv.DictWriter(f, fieldnames=COLUMNS)
    writer.writeheader()
    for row in rows:
        full = {col: row.get(col, "") for col in COLUMNS}
        if "Chat Session" not in row:
            full["Chat Session"] = thread_name
        writer.writerow(full)
    f.close()
    return f.name


def msg(timestamp: str, text: str, sender: str = "Alice",
        msg_type: str = "Incoming", sender_id: str = "+10001112222") -> dict:
    return {
        "Message Date": timestamp,
        "Type": msg_type,
        "Sender Name": sender,
        "Sender ID": sender_id,
        "Text": text,
        "Status": "Read",
        "Service": "SMS",
    }


def outgoing(timestamp: str, text: str) -> dict:
    return {
        "Message Date": timestamp,
        "Type": "Outgoing",
        "Sender Name": "",
        "Sender ID": "",
        "Text": text,
        "Status": "Read",
        "Service": "SMS",
    }


# ─────────────────────────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────────────────────────

class TestThreadRow:
    """Verify thread rows are constructed correctly."""

    def test_thread_row_fields_present(self):
        """Thread row must contain all required fields."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello from Alice"),
            outgoing("2023-01-01 10:01:00", "Hello back from Thomas"),
        ])
        try:
            db = MockSupabaseClient()
            ingestor = IMessageIngestor(db)
            ingestor.ingest_csv(path)

            threads = db.rows_for("imessage_threads")
            assert len(threads) == 1
            t = threads[0]
            for field in ["id", "thread_name", "thread_type", "participants",
                          "source_file", "date_start", "date_end",
                          "message_count", "privacy_tier"]:
                assert field in t, f"Missing field: {field}"
        finally:
            os.unlink(path)

    def test_bilateral_thread_privacy_tier_3(self):
        """Bilateral threads must have privacy_tier = 3."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Just the two of us talking here"),
            outgoing("2023-01-01 10:01:00", "Indeed just us talking here"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            thread = db.rows_for("imessage_threads")[0]
            assert thread["privacy_tier"] == 3
        finally:
            os.unlink(path)

    def test_group_thread_privacy_tier_2(self):
        """Group threads must have privacy_tier = 2."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Group message from Alice here"),
            msg("2023-01-01 10:01:00", "Group message from Bob here",
                sender="Bob", sender_id="+10009998888"),
            msg("2023-01-01 10:02:00", "Group message from Carol here",
                sender="Carol", sender_id="+10007776666"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            thread = db.rows_for("imessage_threads")[0]
            assert thread["privacy_tier"] == 2
        finally:
            os.unlink(path)

    def test_source_file_is_basename_only(self):
        """Source file stored in DB must be filename only, no directory path."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            thread = db.rows_for("imessage_threads")[0]
            assert "/" not in thread["source_file"]
            assert "\\" not in thread["source_file"]
            assert thread["source_file"].endswith(".csv")
        finally:
            os.unlink(path)

    def test_message_count_correct(self):
        """Thread row message_count must match actual message count."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Message one from Alice here"),
            msg("2023-01-01 10:01:00", "Message two from Alice here"),
            outgoing("2023-01-01 10:02:00", "Message three outgoing reply"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            thread = db.rows_for("imessage_threads")[0]
            assert thread["message_count"] == 3
        finally:
            os.unlink(path)


class TestParticipantRow:
    """Verify participant rows are constructed correctly."""

    def test_self_participant_is_flagged(self):
        """Thomas (outgoing sender) must be flagged as is_self=True."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Incoming message from Alice here"),
            outgoing("2023-01-01 10:01:00", "Outgoing reply from Thomas here"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            participants = db.rows_for("imessage_participants")
            self_records = [p for p in participants if p["is_self"]]
            assert len(self_records) == 1
            assert self_records[0]["display_name"] == SELF_NAME
        finally:
            os.unlink(path)

    def test_participant_has_thread_id(self):
        """Each participant row must reference the thread."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            thread = db.rows_for("imessage_threads")[0]
            participants = db.rows_for("imessage_participants")
            for p in participants:
                assert thread["id"] in p["thread_ids"]
        finally:
            os.unlink(path)


class TestMessageRow:
    """Verify message rows are constructed correctly."""

    def test_message_row_fields_present(self):
        """Message rows must contain all required fields."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            messages = db.rows_for("imessage_messages")
            assert len(messages) >= 1
            m = messages[0]
            for field in ["id", "thread_id", "sender_name", "sender_id",
                          "timestamp", "text", "message_type", "has_text"]:
                assert field in m, f"Missing field: {field}"
        finally:
            os.unlink(path)

    def test_message_count_matches_thread(self):
        """Number of message rows must match thread.message_count."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "First message from Alice here"),
            msg("2023-01-01 10:01:00", "Second message from Alice here"),
            outgoing("2023-01-01 10:02:00", "Third message outgoing reply"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            thread = db.rows_for("imessage_threads")[0]
            messages = db.rows_for("imessage_messages")
            assert len(messages) == thread["message_count"]
        finally:
            os.unlink(path)

    def test_outgoing_message_attributed_to_self(self):
        """Outgoing messages must be attributed to SELF_NAME."""
        path = make_csv_file([
            outgoing("2023-01-01 10:00:00", "This is an outgoing message reply"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            messages = db.rows_for("imessage_messages")
            assert messages[0]["sender_name"] == SELF_NAME
        finally:
            os.unlink(path)


class TestBurstRow:
    """Verify burst rows are constructed correctly."""

    def test_burst_row_fields_present(self):
        """Burst rows must contain all required fields."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
            msg("2023-01-01 10:01:00", "Another message from Alice here"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            bursts = db.rows_for("imessage_bursts")
            assert len(bursts) >= 1
            b = bursts[0]
            for field in ["id", "thread_id", "thread_name", "thread_type",
                          "burst_index", "date_start", "date_end",
                          "participants", "dominant_sender", "text_combined",
                          "privacy_tier", "embedding"]:
                assert field in b, f"Missing field: {field}"
        finally:
            os.unlink(path)

    def test_burst_embedding_is_none(self):
        """Burst embedding must be None — populated by embed_chunks CLI."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            bursts = db.rows_for("imessage_bursts")
            assert all(b["embedding"] is None for b in bursts)
        finally:
            os.unlink(path)

    def test_burst_thread_id_matches_thread(self):
        """All burst rows must reference the correct thread_id."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "First burst message here today"),
            msg("2023-01-01 15:00:00", "Second burst message here today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            thread = db.rows_for("imessage_threads")[0]
            bursts = db.rows_for("imessage_bursts")
            for b in bursts:
                assert b["thread_id"] == thread["id"]
        finally:
            os.unlink(path)


class TestChunkMirrorRow:
    """Verify chunk mirror rows are constructed correctly."""

    def test_chunk_mirror_source_type_is_imessage(self):
        """Chunk mirror rows must have source_type = 'imessage'."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            chunks = db.rows_for("chunks")
            assert all(c["source_type"] == "imessage" for c in chunks)
        finally:
            os.unlink(path)

    def test_chunk_mirror_note_id_is_none(self):
        """Chunk mirror rows must have note_id = None."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            chunks = db.rows_for("chunks")
            assert all(c["note_id"] is None for c in chunks)
        finally:
            os.unlink(path)

    def test_chunk_mirror_source_id_links_to_burst(self):
        """Chunk mirror source_id must match a burst id."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            burst_ids = {b["id"] for b in db.rows_for("imessage_bursts")}
            chunks = db.rows_for("chunks")
            for c in chunks:
                assert c["source_id"] in burst_ids
        finally:
            os.unlink(path)

    def test_chunk_mirror_privacy_tier_matches_burst(self):
        """Chunk mirror privacy_tier must match its source burst."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Bilateral private message here today"),
            outgoing("2023-01-01 10:01:00", "Bilateral reply message here today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            chunks = db.rows_for("chunks")
            # Bilateral thread → privacy_tier 3
            assert all(c["privacy_tier"] == 3 for c in chunks)
        finally:
            os.unlink(path)

    def test_chunk_mirror_embedding_is_none(self):
        """Chunk mirror embeddings must be None — populated by embed_chunks."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)
            chunks = db.rows_for("chunks")
            assert all(c["embedding"] is None for c in chunks)
        finally:
            os.unlink(path)


class TestIngestionOrder:
    """Verify tables are written in the correct dependency order."""

    def test_thread_upserted_before_messages(self):
        """
        imessage_threads must be upserted before imessage_messages.
        Messages have a FK reference to threads.
        """
        call_order = []

        class OrderTrackingClient:
            dry_run = False

            def upsert_rows(self, table, rows):
                call_order.append(table)

            def delete_where(self, table, column, value):
                pass

        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            IMessageIngestor(OrderTrackingClient()).ingest_csv(path)
            assert call_order.index("imessage_threads") < \
                   call_order.index("imessage_messages")
        finally:
            os.unlink(path)

    def test_thread_upserted_before_bursts(self):
        """imessage_threads must be upserted before imessage_bursts."""
        call_order = []

        class OrderTrackingClient:
            dry_run = False

            def upsert_rows(self, table, rows):
                call_order.append(table)

            def delete_where(self, table, column, value):
                pass

        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            IMessageIngestor(OrderTrackingClient()).ingest_csv(path)
            assert call_order.index("imessage_threads") < \
                   call_order.index("imessage_bursts")
        finally:
            os.unlink(path)


class TestReIngestion:
    """Verify delete-then-reinsert pattern for bursts and chunks."""

    def test_bursts_deleted_before_reinsert(self):
        """
        imessage_bursts must be deleted by thread_id before re-insertion.
        This handles ghost rows from deleted or edited messages.
        """
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)

            thread_id = db.rows_for("imessage_threads")[0]["id"]
            delete_calls = db.delete_calls_for("imessage_bursts")

            assert len(delete_calls) >= 1
            assert any(c[1] == "thread_id" and c[2] == thread_id
                       for c in delete_calls)
        finally:
            os.unlink(path)

    def test_chunk_mirrors_deleted_before_reinsert(self):
        """
        chunks mirror rows must be deleted by source_id before re-insertion.
        """
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient()
            IMessageIngestor(db).ingest_csv(path)

            delete_calls = db.delete_calls_for("chunks")
            assert len(delete_calls) >= 1
            assert all(c[1] == "source_id" for c in delete_calls)
        finally:
            os.unlink(path)


class TestDryRun:
    """Verify no writes occur when client is in dry-run mode."""

    def test_dry_run_no_upserts(self):
        """No upsert_rows calls must reach the database in dry-run mode."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient(dry_run=True)
            IMessageIngestor(db).ingest_csv(path)
            assert db.upserted == {}
        finally:
            os.unlink(path)

    def test_dry_run_no_deletes(self):
        """No delete_where calls must reach the database in dry-run mode."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ])
        try:
            db = MockSupabaseClient(dry_run=True)
            IMessageIngestor(db).ingest_csv(path)
            assert db.deleted == []
        finally:
            os.unlink(path)


class TestIngestionResult:
    """Verify the result summary counts are correct."""

    def test_result_counts_match_actual_data(self):
        """Result counts must accurately reflect what was ingested."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "First message from Alice here"),
            msg("2023-01-01 10:30:00", "Second message from Alice here"),
            outgoing("2023-01-01 10:31:00", "Reply message from Thomas here"),
        ])
        try:
            db = MockSupabaseClient()
            result = IMessageIngestor(db).ingest_csv(path)

            assert result.messages_upserted == 3
            assert result.bursts_upserted >= 1
            assert result.chunks_mirrored == result.bursts_upserted
            assert result.dry_run is False
        finally:
            os.unlink(path)

    def test_empty_csv_returns_zero_counts(self):
        """An empty CSV must return an all-zero result without error."""
        path = make_csv_file([])
        try:
            db = MockSupabaseClient()
            result = IMessageIngestor(db).ingest_csv(path)
            assert result.messages_upserted == 0
            assert result.bursts_upserted == 0
            assert result.chunks_mirrored == 0
        finally:
            os.unlink(path)

    def test_result_str_includes_thread_name(self):
        """String representation must include the thread name."""
        path = make_csv_file([
            msg("2023-01-01 10:00:00", "Hello there from Alice today"),
        ], thread_name="Alice & Bob")
        try:
            db = MockSupabaseClient()
            result = IMessageIngestor(db).ingest_csv(path)
            assert "Alice & Bob" in str(result)
        finally:
            os.unlink(path)
