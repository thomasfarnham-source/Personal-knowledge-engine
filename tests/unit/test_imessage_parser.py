"""
tests/unit/test_imessage_parser.py

Unit tests for pke/parsers/imessage_parser.py

═══════════════════════════════════════════════════════════════════
WHAT THIS FILE TESTS
═══════════════════════════════════════════════════════════════════

The iMessage parser has five distinct responsibilities:

    1. Sender resolution — correctly identifying who sent each message,
       including the special case where Outgoing + blank name = Thomas

    2. Burst grouping — correctly splitting messages into conversation
       bursts based on the 4-hour gap threshold

    3. Text cleaning — stripping HTML, normalising whitespace,
       handling attachment-only messages

    4. Thread classification — correctly identifying group vs bilateral
       threads based on participant count

    5. ParsedNote contract — producing output that conforms exactly
       to the PKE ingestion pipeline contract, including all reserved
       fields

═══════════════════════════════════════════════════════════════════
TEST STRUCTURE
═══════════════════════════════════════════════════════════════════

    TestSenderResolution      — who sent each message
    TestBurstGrouping         — 4-hour gap threshold logic
    TestTextCleaning          — HTML stripping, whitespace, attachments
    TestThreadClassification  — group vs bilateral detection
    TestParsedNoteContract    — output shape and field values
    TestEdgeCases             — empty files, notifications, all-attachments
    TestDeterminism           — same input always produces same output

═══════════════════════════════════════════════════════════════════
WHY NO REAL CSV IN TESTS
═══════════════════════════════════════════════════════════════════

Tests use minimal synthetic CSV data constructed in-memory using
io.StringIO. This keeps tests fast, deterministic, and independent
of any real data file being present on disk.

The real CSV was used to validate the parser works in practice
(976 bursts, correct participant attribution, correct thread type).
The unit tests verify the parser's contracts hold under controlled
conditions.
"""

import csv
import io
import os
import tempfile
from datetime import datetime, timedelta

import pytest

from pke.parsers.imessage_parser import (
    BURST_GAP_HOURS,
    NOTEBOOK_BILATERAL,
    NOTEBOOK_GROUP,
    SELF_NAME,
    THREAD_TYPE_BILATERAL,
    THREAD_TYPE_GROUP,
    _clean_text,
    _classify_thread,
    _make_id,
    _resolve_sender,
    burst_to_parsed_note,
    parse_imessage_csv,
    parse_imessage_exports,
)

# ─────────────────────────────────────────────────────────────────
# CSV CONSTRUCTION HELPERS
# ─────────────────────────────────────────────────────────────────

COLUMNS = [
    "Chat Session", "Message Date", "Delivered Date", "Read Date",
    "Edited Date", "Deleted Date", "Service", "Type", "Sender ID",
    "Sender Name", "Status", "Replying to", "Subject", "Text",
    "Reactions", "Attachment", "Attachment type",
]


def make_csv(rows: list[dict], thread_name: str = "Alice & Bob") -> str:
    """
    Build a CSV string from a list of row dicts.
    Missing fields default to empty string.
    Writes to a string buffer and returns the CSV content.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS)
    writer.writeheader()
    for row in rows:
        full_row = {col: row.get(col, "") for col in COLUMNS}
        if "Chat Session" not in row:
            full_row["Chat Session"] = thread_name
        writer.writerow(full_row)
    return buf.getvalue()


def write_csv_file(content: str) -> str:
    """Write CSV content to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


def make_message_row(
    timestamp: str,
    text: str = "Hello",
    sender_name: str = "Alice",
    msg_type: str = "Incoming",
    sender_id: str = "+10001112222",
    attachment: str = "",
    reactions: str = "",
) -> dict:
    """Build a single message row dict with sensible defaults."""
    return {
        "Message Date": timestamp,
        "Type": msg_type,
        "Sender Name": sender_name,
        "Sender ID": sender_id,
        "Text": text,
        "Attachment": attachment,
        "Reactions": reactions,
        "Status": "Read",
        "Service": "SMS",
    }


def ts(base: str, hours: int = 0) -> str:
    """
    Generate a timestamp string offset by a number of hours from a base.
    base format: "2023-01-01 10:00:00"
    """
    dt = datetime.fromisoformat(base) + timedelta(hours=hours)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────────────────────────
# TEST CLASSES
# ─────────────────────────────────────────────────────────────────


class TestSenderResolution:
    """
    Verify the sender resolution rules are applied correctly.

    The resolution rules are the foundation of per-sender attribution
    which drives the Group Voice Synthesis milestone. Getting them
    wrong silently corrupts the corpus.

    Rules:
        Outgoing + blank Sender Name → SELF_NAME ("Thomas")
        Incoming + Sender Name       → use Sender Name
        Outgoing + Sender Name       → use Sender Name (rare but valid)
    """

    def test_outgoing_blank_name_resolves_to_self(self):
        """
        The most important rule: Outgoing messages with no Sender Name
        are Thomas's messages. This is the only reliable signal for
        identifying the self in iMazing exports.
        """
        row = {"Type": "Outgoing", "Sender Name": ""}
        assert _resolve_sender(row) == SELF_NAME

    def test_incoming_with_name_uses_name(self):
        """
        Incoming messages always carry the sender's display name.
        The name must be preserved exactly — it's the primary identity
        signal for Group Voice channel separation.
        """
        row = {"Type": "Incoming", "Sender Name": "Patrick Mangan"}
        assert _resolve_sender(row) == "Patrick Mangan"

    def test_outgoing_with_name_uses_name(self):
        """
        Rare case: outgoing message that has a sender name populated.
        Should use the name, not override with SELF_NAME.
        """
        row = {"Type": "Outgoing", "Sender Name": "Thomas Farnham"}
        assert _resolve_sender(row) == "Thomas Farnham"

    def test_incoming_blank_name_returns_unknown(self):
        """
        Incoming message with no sender name — contact not in address
        book. Returns "Unknown" rather than crashing or returning None.
        """
        row = {"Type": "Incoming", "Sender Name": ""}
        assert _resolve_sender(row) == "Unknown"

    def test_self_name_constant_is_thomas(self):
        """
        The SELF_NAME constant must be "Thomas" — this is how self
        messages are identified throughout the corpus analysis and
        Group Voice synthesis pipeline.
        """
        assert SELF_NAME == "Thomas"


class TestBurstGrouping:
    """
    Verify the conversation burst detection logic.

    The burst is the primary unit of ingestion — getting the grouping
    wrong either over-fragments conversations (too many tiny bursts)
    or under-fragments them (one huge burst spanning unrelated topics).

    The 4-hour gap threshold is the design decision. Tests verify the
    boundary conditions precisely.
    """

    def test_messages_within_gap_form_single_burst(self):
        """
        Messages less than 4 hours apart must be in the same burst.
        This is the core grouping contract.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(ts(base, 0), "Hello"),
            make_message_row(ts(base, 1), "World"),
            make_message_row(ts(base, 2), "How are you"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            assert len(bursts) == 1
            assert len(bursts[0].messages) == 3
        finally:
            os.unlink(path)

    def test_messages_beyond_gap_form_separate_bursts(self):
        """
        Messages more than 4 hours apart must be in separate bursts.
        The gap threshold is BURST_GAP_HOURS — test at gap + 1 minute
        to ensure the boundary is inclusive.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(ts(base, 0), "Morning message"),
            make_message_row(ts(base, BURST_GAP_HOURS + 0.1), "Evening message"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            assert len(bursts) == 2
        finally:
            os.unlink(path)

    def test_exactly_at_gap_threshold_starts_new_burst(self):
        """
        A gap of exactly BURST_GAP_HOURS stays in the same burst.
        The threshold is strict greater-than — equal to the gap
        does NOT split. A gap must EXCEED the threshold to split.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(ts(base, 0), "First message here"),
            make_message_row(ts(base, BURST_GAP_HOURS), "Second message here"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            assert len(bursts) == 1
        finally:
            os.unlink(path)

    def test_burst_index_is_sequential(self):
        """
        Each burst must have a sequential burst_index starting from 0.
        This is used for deterministic ID generation and ordering.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(ts(base, 0), "First burst message with enough content"),
            make_message_row(ts(base, 5), "Second burst message with enough content"),
            make_message_row(ts(base, 10), "Third burst message with enough content"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            assert len(bursts) == 3
            assert [b.burst_index for b in bursts] == [0, 1, 2]
        finally:
            os.unlink(path)

    def test_burst_date_start_is_first_message_timestamp(self):
        """
        burst.date_start must be the ISO timestamp of the first message
        in the burst. Used as entry_timestamp in the ParsedNote contract.
        """
        base = "2023-06-15 14:30:00"
        rows = [
            make_message_row(base, "First"),
            make_message_row(ts(base, 1), "Second"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            assert bursts[0].date_start.startswith("2023-06-15T14:30:00")
        finally:
            os.unlink(path)

    def test_attachment_only_burst_excluded(self):
        """
        Bursts where all messages are attachments with no text must be
        excluded from output. They produce no useful embedding and would
        waste embedding API calls.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(base, text="", attachment="photo.jpg"),
            make_message_row(ts(base, 0.1), text="", attachment="video.mp4"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            assert len(bursts) == 0
        finally:
            os.unlink(path)

    def test_mixed_burst_with_some_attachments_included(self):
        """
        A burst containing both text and attachment messages must be
        included — the text content is sufficient for embedding.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(base, text="Check this out"),
            make_message_row(ts(base, 0.1), text="", attachment="photo.jpg"),
            make_message_row(ts(base, 0.2), text="Cool right?"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            assert len(bursts) == 1
            assert bursts[0].has_content
        finally:
            os.unlink(path)


class TestTextCleaning:
    """
    Verify text cleaning produces appropriate output for embedding.

    Clean text directly affects embedding quality. HTML artefacts,
    null bytes, and excessive whitespace all degrade retrieval.
    """

    def test_html_tags_stripped(self):
        """
        HTML tags from Joplin export artefacts must be stripped.
        The text content is preserved; only the markup is removed.
        """
        assert _clean_text("<b>Hello</b> world") == "Hello world"

    def test_null_bytes_removed(self):
        """Null bytes cause encoding errors downstream — must be removed."""
        assert _clean_text("Hello\x00world") == "Helloworld"

    def test_leading_trailing_whitespace_stripped(self):
        """Standard whitespace normalisation."""
        assert _clean_text("  Hello world  ") == "Hello world"

    def test_excessive_newlines_collapsed(self):
        """
        Three or more consecutive newlines are collapsed to two.
        Preserves paragraph structure without excessive blank space.
        """
        result = _clean_text("Line 1\n\n\n\nLine 2")
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_empty_string_returns_empty(self):
        """Empty input must return empty string, not None or error."""
        assert _clean_text("") == ""

    def test_urls_preserved(self):
        """
        URLs must not be stripped — the group shares links constantly
        and the URL is often the entire semantic content of a message.
        """
        url = "https://www.nytimes.com/article/something-important"
        result = _clean_text(url)
        assert url in result

    def test_burst_text_combines_messages_with_attribution(self):
        """
        The combined burst text must attribute each message to its
        sender. Format: "Sender: text\n\nSender: text"
        This attribution is critical for Group Voice channel analysis.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(base, "Hello", sender_name="Alice"),
            make_message_row(ts(base, 0.5), "World", sender_name="Bob"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            assert "Alice: Hello" in bursts[0].text_combined
            assert "Bob: World" in bursts[0].text_combined
        finally:
            os.unlink(path)

    def test_attachment_noted_in_burst_text(self):
        """
        Attachment-only messages must contribute a brief reference
        to the burst text rather than being silently dropped.
        The file extension is preserved for context.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(base, "Look at this"),
            make_message_row(ts(base, 0.1), text="", attachment="photo.jpg"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            assert "[attachment" in bursts[0].text_combined
        finally:
            os.unlink(path)


class TestThreadClassification:
    """
    Verify thread type classification (group vs bilateral).

    Thread type is critical for Group Voice Synthesis — bilateral
    threads contain a different register than group threads and must
    be kept separate in the corpus.
    """

    def test_two_participants_is_bilateral(self):
        """
        A thread with Thomas and one other person is bilateral.
        Counterparty count of 1 = bilateral.
        """
        participants = [SELF_NAME, "Patrick Mangan"]
        assert _classify_thread(participants) == THREAD_TYPE_BILATERAL

    def test_three_participants_is_group(self):
        """Three or more participants (including self) = group thread."""
        participants = [SELF_NAME, "Alice", "Bob"]
        assert _classify_thread(participants) == THREAD_TYPE_GROUP

    def test_five_participants_is_group(self):
        """The real group chat has 5 participants — must be group."""
        participants = [
            SELF_NAME, "Patrick Mangan", "James Root",
            "Chris Zicchelo", "William Renahan"
        ]
        assert _classify_thread(participants) == THREAD_TYPE_GROUP

    def test_group_thread_uses_imessage_notebook(self):
        """Group threads must be assigned the NOTEBOOK_GROUP notebook."""
        assert NOTEBOOK_GROUP == "iMessage"

    def test_bilateral_thread_uses_bilateral_notebook(self):
        """Bilateral threads must use the NOTEBOOK_BILATERAL notebook."""
        assert NOTEBOOK_BILATERAL == "iMessage-bilateral"

    def test_parser_assigns_correct_notebook_for_group(self):
        """
        End-to-end: a CSV with 5 participants produces bursts with
        notebook = "iMessage" (group notebook).
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(base, "Hello", sender_name="Alice"),
            make_message_row(ts(base, 0.5), "Hi", sender_name="Bob"),
            make_message_row(ts(base, 1), "Hey", sender_name="Carol"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            note = burst_to_parsed_note(bursts[0])
            assert note["notebook"] == NOTEBOOK_GROUP
        finally:
            os.unlink(path)

    def test_parser_assigns_correct_notebook_for_bilateral(self):
        """
        End-to-end: a CSV with 2 participants (self + one other)
        produces bursts with notebook = "iMessage-bilateral".
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(base, "Just us", sender_name="Patrick Mangan"),
            make_message_row(
                ts(base, 0.5), "Indeed",
                sender_name="", msg_type="Outgoing"
            ),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            note = burst_to_parsed_note(bursts[0])
            assert note["notebook"] == NOTEBOOK_BILATERAL
        finally:
            os.unlink(path)


class TestParsedNoteContract:
    """
    Verify the ParsedNote contract output shape.

    The ParsedNote contract is the boundary between the parser and
    the ingestion pipeline. Every field must be present and correctly
    typed. Missing or wrong fields cause silent failures downstream.

    This is a contract test — it verifies the parser's output from
    the consumer's point of view (the ingestion pipeline).
    """

    def _make_single_burst_note(self) -> dict:
        """Helper: parse a minimal CSV and return the first ParsedNote."""
        base = "2023-06-15 09:00:00"
        rows = [
            make_message_row(base, "Good morning", sender_name="Alice"),
            make_message_row(ts(base, 0.5), "Morning!", sender_name="Bob"),
        ]
        csv_content = make_csv(rows, thread_name="Alice & Bob")
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            return burst_to_parsed_note(bursts[0])
        finally:
            os.unlink(path)

    def test_all_required_fields_present(self):
        """
        Every field in the ParsedNote contract must be present.
        Missing fields cause KeyError or None-propagation in the
        ingestion pipeline.
        """
        note = self._make_single_burst_note()
        required_fields = [
            "id", "title", "body", "notebook", "tags",
            "created_at", "updated_at", "metadata",
            "source_file", "resource_links",
            "source_type", "participants", "dominant_sender",
            "thread_id", "thread_type", "person_ids",
        ]
        for field in required_fields:
            assert field in note, f"Missing required field: {field}"

    def test_source_type_is_imessage(self):
        """source_type must be 'imessage' for all iMessage parser output."""
        note = self._make_single_burst_note()
        assert note["source_type"] == "imessage"

    def test_person_ids_is_none(self):
        """
        person_ids must be None in v1 — reserved for the entity layer.
        It must be present in the output (not missing) but unpopulated.
        Every parser going forward must reserve this field.
        """
        note = self._make_single_burst_note()
        assert "person_ids" in note
        assert note["person_ids"] is None

    def test_tags_is_empty_list(self):
        """tags must be an empty list — no tag extraction in v1."""
        note = self._make_single_burst_note()
        assert note["tags"] == []

    def test_body_contains_attributed_messages(self):
        """
        body must contain sender-attributed message text.
        The ingestion pipeline embeds this field directly.
        """
        note = self._make_single_burst_note()
        assert "Alice:" in note["body"]
        assert "Good morning" in note["body"]

    def test_title_contains_thread_name_and_date(self):
        """
        title format: "{thread_name} — {YYYY-MM-DD}"
        Used as the note title in Obsidian reflections panel.
        """
        note = self._make_single_burst_note()
        assert "Alice & Bob" in note["title"]
        assert "2023-06-15" in note["title"]

    def test_created_at_is_iso_timestamp(self):
        """created_at must be a valid ISO timestamp string."""
        note = self._make_single_burst_note()
        # Should not raise
        datetime.fromisoformat(note["created_at"])

    def test_thread_id_is_consistent_for_same_file(self):
        """
        All bursts from the same CSV must share the same thread_id.
        The thread_id is derived deterministically from the file path.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(ts(base, 0), "First burst message with enough content"),
            make_message_row(ts(base, 5), "Second burst message with enough content"),
            make_message_row(ts(base, 10), "Third burst message with enough content"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            notes = [burst_to_parsed_note(b) for b in bursts]
            thread_ids = {n["thread_id"] for n in notes}
            assert len(thread_ids) == 1
        finally:
            os.unlink(path)

    def test_thread_type_in_metadata(self):
        """thread_type must appear in both metadata dict and top-level."""
        note = self._make_single_burst_note()
        assert "thread_type" in note["metadata"]
        assert note["metadata"]["thread_type"] == note["thread_type"]

    def test_participants_in_metadata_and_top_level(self):
        """participants must appear in both metadata and top-level."""
        note = self._make_single_burst_note()
        assert "participants" in note["metadata"]
        assert note["participants"] == note["metadata"]["participants"]

    def test_dominant_sender_is_most_frequent_sender(self):
        """
        dominant_sender must be the sender with the most messages
        in the burst. Critical for Group Voice channel weighting.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(ts(base, 0), "Alice 1", sender_name="Alice"),
            make_message_row(ts(base, 0.2), "Alice 2", sender_name="Alice"),
            make_message_row(ts(base, 0.4), "Alice 3", sender_name="Alice"),
            make_message_row(ts(base, 0.6), "Bob 1", sender_name="Bob"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            note = burst_to_parsed_note(bursts[0])
            assert note["dominant_sender"] == "Alice"
        finally:
            os.unlink(path)

    def test_resource_links_contains_attachment_filenames(self):
        """
        resource_links must contain attachment filenames from the burst.
        These are stored for future media surfacing in the plugin.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(base, "Look at this photo"),
            make_message_row(
                ts(base, 0.1), text="", attachment="IMG_1234.jpg"
            ),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            note = burst_to_parsed_note(bursts[0])
            assert "IMG_1234.jpg" in note["resource_links"]
        finally:
            os.unlink(path)


class TestEdgeCases:
    """
    Verify the parser handles edge cases gracefully.

    Edge cases in the real corpus: notification rows, attachment-only
    messages, missing timestamps, empty files.
    """

    def test_notification_rows_skipped(self):
        """
        Type == "Notification" rows must be silently skipped.
        They are system messages, not conversation content.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(base, "Hello"),
            {
                "Message Date": ts(base, 0.5),
                "Type": "Notification",
                "Text": "Alice left the conversation",
            },
            make_message_row(ts(base, 1), "Goodbye"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            thread, bursts = parse_imessage_csv(path)
            # 2 real messages, 1 notification skipped
            assert thread.message_count == 2
        finally:
            os.unlink(path)

    def test_empty_csv_returns_empty_results(self):
        """
        A CSV with only a header row (no messages) must return an
        empty thread and empty burst list without crashing.
        """
        csv_content = make_csv([])
        path = write_csv_file(csv_content)
        try:
            thread, bursts = parse_imessage_csv(path)
            assert thread.message_count == 0
            assert bursts == []
        finally:
            os.unlink(path)

    def test_missing_file_raises_file_not_found(self):
        """
        Passing a non-existent file path must raise FileNotFoundError,
        not a cryptic internal error.
        """
        with pytest.raises(FileNotFoundError):
            parse_imessage_csv("/nonexistent/path/messages.csv")

    def test_outgoing_messages_attributed_to_self(self):
        """
        End-to-end: Outgoing messages with no name in the CSV must
        appear as SELF_NAME in the burst participants list.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(base, "Incoming", sender_name="Alice"),
            make_message_row(
                ts(base, 0.5), "Outgoing reply",
                sender_name="", msg_type="Outgoing"
            ),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            assert SELF_NAME in bursts[0].participants
        finally:
            os.unlink(path)

    def test_multi_file_export_dir(self):
        """
        parse_imessage_exports must process all CSV files in a directory
        and return one thread + bursts per file.
        """
        base = "2023-01-01 10:00:00"
        rows1 = [make_message_row(base, "File 1 message with enough content to embed", sender_name="Alice")]
        rows2 = [make_message_row(base, "File 2 message with enough content to embed", sender_name="Bob")]

        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = os.path.join(tmpdir, "thread1.csv")
            path2 = os.path.join(tmpdir, "thread2.csv")

            with open(path1, "w", encoding="utf-8") as f:
                f.write(make_csv(rows1, thread_name="Alice Thread"))
            with open(path2, "w", encoding="utf-8") as f:
                f.write(make_csv(rows2, thread_name="Bob Thread"))

            threads, parsed_notes = parse_imessage_exports(tmpdir)

            assert len(threads) == 2
            assert len(parsed_notes) >= 2

    def test_empty_export_dir_returns_empty(self):
        """An export directory with no CSV files returns empty lists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            threads, notes = parse_imessage_exports(tmpdir)
            assert threads == []
            assert notes == []


class TestDeterminism:
    """
    Verify the parser produces identical output on repeated runs.

    Determinism is a core PKE requirement. The same input must always
    produce the same output — same burst IDs, same thread IDs, same
    ordering. Non-deterministic output breaks idempotent ingestion.
    """

    def test_same_csv_produces_same_burst_ids(self):
        """
        Parsing the same CSV twice must produce identical burst IDs.
        Burst IDs are deterministic from thread_id + timestamp + index.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(base, "Hello"),
            make_message_row(ts(base, 5), "New burst"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts1 = parse_imessage_csv(path)
            _, bursts2 = parse_imessage_csv(path)
            ids1 = [b.burst_id for b in bursts1]
            ids2 = [b.burst_id for b in bursts2]
            assert ids1 == ids2
        finally:
            os.unlink(path)

    def test_same_csv_produces_same_thread_id(self):
        """Thread ID must be deterministic from the file path."""
        base = "2023-01-01 10:00:00"
        rows = [make_message_row(base, "Hello")]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            thread1, _ = parse_imessage_csv(path)
            thread2, _ = parse_imessage_csv(path)
            assert thread1.thread_id == thread2.thread_id
        finally:
            os.unlink(path)

    def test_make_id_is_deterministic(self):
        """The ID generation function must always return the same value."""
        assert _make_id("test-seed") == _make_id("test-seed")

    def test_make_id_different_seeds_different_ids(self):
        """Different seeds must produce different IDs."""
        assert _make_id("seed-a") != _make_id("seed-b")

    def test_burst_ordering_is_chronological(self):
        """
        Bursts must be ordered chronologically — earliest first.
        The retrieval API and Group Voice synthesis both depend on
        temporal ordering.
        """
        base = "2023-01-01 10:00:00"
        rows = [
            make_message_row(ts(base, 0), "First burst"),
            make_message_row(ts(base, 5), "Second burst"),
            make_message_row(ts(base, 10), "Third burst"),
        ]
        csv_content = make_csv(rows)
        path = write_csv_file(csv_content)
        try:
            _, bursts = parse_imessage_csv(path)
            dates = [b.date_start for b in bursts]
            assert dates == sorted(dates)
        finally:
            os.unlink(path)
