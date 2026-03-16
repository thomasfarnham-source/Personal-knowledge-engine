"""
pke/ingestion/imessage_ingestor.py

Ingests parsed iMessage data into Supabase.

═══════════════════════════════════════════════════════════════════
WHAT THIS FILE DOES
═══════════════════════════════════════════════════════════════════

Takes the output of pke/parsers/imessage_parser.py and writes it
to the four iMessage tables plus the chunks mirror.

Ingestion order (dependency-safe):
    1. imessage_threads      — must exist before messages/bursts
    2. imessage_participants  — identity registry
    3. imessage_messages     — atomic message records
    4. imessage_bursts       — conversation bursts
    5. chunks (mirror)       — unified retrieval surface

All operations use SupabaseClient methods — same patterns as the
existing Joplin ingestion pipeline.

═══════════════════════════════════════════════════════════════════
RE-INGESTION STRATEGY
═══════════════════════════════════════════════════════════════════

On re-ingest from an updated CSV export:
    - imessage_threads:      upsert (updates date_end, message_count)
    - imessage_participants: upsert (updates thread_ids)
    - imessage_messages:     upsert (new messages inserted, existing
                             rows overwritten — identical in practice)
    - imessage_bursts:       delete_where(thread_id) then re-insert.
                             Handles deleted/edited messages that
                             would otherwise leave ghost burst rows.
    - chunks mirror:         delete_where(source_id) per burst,
                             then re-insert to match updated bursts.

The delete-then-reinsert pattern is safe because:
    - The database is an index, never an archive
    - Source CSV files are the permanent record
    - Date-stamped exports are kept permanently

═══════════════════════════════════════════════════════════════════
RELATIONSHIP TO OTHER FILES
═══════════════════════════════════════════════════════════════════

    pke/parsers/imessage_parser.py  — produces the data we ingest
    pke/supabase_client.py          — database client (injected)
    pke/cli/ingest_imessage.py      — CLI entry point
    pke/ingestion/orchestrator.py   — Joplin ingestion (parallel)
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from pke.parsers.imessage_parser import (
    SELF_NAME,
    IMessageBurst,
    IMessageMessage,
    IMessageThread,
    _make_id,
    parse_imessage_csv,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# INGESTION RESULT
# ─────────────────────────────────────────────────────────────────

@dataclass
class IMessageIngestionResult:
    """Summary of a completed ingestion run."""
    thread_id: str
    thread_name: str
    messages_upserted: int
    bursts_upserted: int
    chunks_mirrored: int
    participants_upserted: int
    skipped_bursts: int
    dry_run: bool

    def __str__(self) -> str:
        mode = "[DRY RUN] " if self.dry_run else ""
        return (
            f"{mode}{self.thread_name}: "
            f"{self.messages_upserted} messages, "
            f"{self.bursts_upserted} bursts, "
            f"{self.chunks_mirrored} chunks mirrored, "
            f"{self.skipped_bursts} bursts skipped (no text)"
        )


# ─────────────────────────────────────────────────────────────────
# CORE INGESTOR
# ─────────────────────────────────────────────────────────────────

class IMessageIngestor:
    """
    Ingests parsed iMessage data into Supabase.

    Receives a SupabaseClient instance — same dependency injection
    pattern as the existing Joplin orchestrator.

    Usage:
        from pke.supabase_client import SupabaseClient
        db = SupabaseClient(client=supabase_client)
        ingestor = IMessageIngestor(db)
        result = ingestor.ingest_csv("path/to/export.csv")
        print(result)

    Dry run:
        db = SupabaseClient(dry_run=True)
        result = ingestor.ingest_csv("path/to/export.csv")
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    # ── Public entry points ──────────────────────────────────────

    def ingest_csv(self, csv_path: str) -> IMessageIngestionResult:
        """
        Ingest a single iMazing CSV export.

        Args:
            csv_path: absolute path to the CSV file

        Returns:
            IMessageIngestionResult with summary counts

        Dry-run behaviour is controlled by the SupabaseClient
        instance passed at construction — no separate dry_run flag.
        """
        logger.info(f"Ingesting {csv_path}")

        thread, bursts = parse_imessage_csv(csv_path)

        if not thread.message_count:
            logger.warning(f"No messages parsed from {csv_path} — skipping")
            return IMessageIngestionResult(
                thread_id=thread.thread_id,
                thread_name=thread.thread_name,
                messages_upserted=0,
                bursts_upserted=0,
                chunks_mirrored=0,
                participants_upserted=0,
                skipped_bursts=0,
                dry_run=self.db.dry_run,
            )

        return self._ingest_thread(thread, bursts)

    def ingest_directory(self, export_dir: str) -> list[IMessageIngestionResult]:
        """
        Ingest all CSV exports in a directory.

        Args:
            export_dir: path to folder containing iMazing CSV exports

        Returns:
            list of IMessageIngestionResult, one per CSV file
        """
        from pathlib import Path

        export_path = Path(export_dir)
        csv_files = sorted(export_path.glob("*.csv"))

        if not csv_files:
            logger.warning(f"No CSV files found in {export_dir}")
            return []

        logger.info(f"Found {len(csv_files)} CSV file(s) in {export_dir}")

        results = []
        for csv_file in csv_files:
            try:
                result = self.ingest_csv(str(csv_file))
                results.append(result)
                logger.info(f"  {result}")
            except Exception as e:
                logger.error(f"Failed to ingest {csv_file.name}: {e}")
                raise

        return results

    # ── Internal pipeline ────────────────────────────────────────

    def _ingest_thread(
        self,
        thread: IMessageThread,
        bursts: list[IMessageBurst],
    ) -> IMessageIngestionResult:
        """Full ingestion pipeline for one thread."""

        # Step 1 — thread metadata
        self._upsert_thread(thread)

        # Step 2 — participants
        participants_upserted = self._upsert_participants(thread)

        # Step 3 — messages
        all_messages = []
        for burst in bursts:
            all_messages.extend(burst.messages)
        messages_upserted = self._upsert_messages(all_messages, thread.thread_id)

        # Step 4 — bursts (delete + reinsert)
        logger.debug(f"Deleting existing bursts for thread {thread.thread_id}")
        self.db.delete_where("imessage_bursts", "thread_id", thread.thread_id)

        content_bursts = [b for b in bursts if b.has_content]
        skipped_bursts = len(bursts) - len(content_bursts)

        burst_rows = [self._burst_to_row(b) for b in content_bursts]
        if burst_rows:
            self.db.upsert_rows("imessage_bursts", burst_rows)
        bursts_upserted = len(burst_rows)

        logger.info(
            f"Upserted {bursts_upserted} bursts for {thread.thread_name} "
            f"({skipped_bursts} skipped)"
        )

        # Step 5 — chunks mirror (delete + reinsert)
        chunks_mirrored = self._mirror_bursts_to_chunks(content_bursts, thread)

        return IMessageIngestionResult(
            thread_id=thread.thread_id,
            thread_name=thread.thread_name,
            messages_upserted=messages_upserted,
            bursts_upserted=bursts_upserted,
            chunks_mirrored=chunks_mirrored,
            participants_upserted=participants_upserted,
            skipped_bursts=skipped_bursts,
            dry_run=self.db.dry_run,
        )

    # ── Step implementations ──────────────────────────────────────

    def _upsert_thread(self, thread: IMessageThread) -> None:
        row = {
            "id":            thread.thread_id,
            "thread_name":   thread.thread_name,
            "thread_type":   thread.thread_type,
            "participants":  thread.participants,
            "source_file":   _basename(thread.source_file),
            "date_start":    thread.date_start,
            "date_end":      thread.date_end,
            "message_count": thread.message_count,
            "privacy_tier":  3 if thread.thread_type == "bilateral" else 2,
        }
        logger.debug(f"Upserting thread: {thread.thread_name}")
        self.db.upsert_rows("imessage_threads", [row])

    def _upsert_participants(self, thread: IMessageThread) -> int:
        rows = []
        for name in thread.participants:
            rows.append({
                "id":           _make_id(name),
                "display_name": name,
                "is_self":      name == SELF_NAME,
                "thread_ids":   [thread.thread_id],
            })
        if rows:
            self.db.upsert_rows("imessage_participants", rows)
        logger.debug(f"Upserted {len(rows)} participants")
        return len(rows)

    def _upsert_messages(
        self,
        messages: list,
        thread_id: str,
    ) -> int:
        rows = [self._message_to_row(msg, thread_id) for msg in messages]
        if rows:
            self.db.upsert_rows("imessage_messages", rows)
        logger.debug(f"Upserted {len(rows)} messages")
        return len(rows)

    def _mirror_bursts_to_chunks(
        self,
        bursts: list,
        thread: IMessageThread,
    ) -> int:
        """
        Mirror each burst as a row in the unified chunks table.
        Delete existing mirror rows first to handle re-ingestion.

        note_id:         NULL — iMessage bursts have no parent note
        source_type:     "imessage"
        source_id:       burst.id — links back to imessage_bursts
        entry_timestamp: burst.date_start — unified timeline
        privacy_tier:    inherited from burst
        embedding:       NULL — populated by embed_chunks CLI
        """
        # Delete existing mirror rows for this thread's bursts
        for burst in bursts:
            self.db.delete_where("chunks", "source_id", burst.burst_id)

        rows = []
        for burst in bursts:
            rows.append({
                "id":              str(uuid.uuid4()),
                "note_id":         None,
                "chunk_index":     burst.burst_index,
                "chunk_text":      burst.text_combined,
                "embedding":       None,
                "char_start":      0,
                "char_end":        len(burst.text_combined),
                "section_title":   burst.thread_name,
                "entry_timestamp": burst.date_start,
                "resource_ids":    burst.resource_links,
                "source_type":     "imessage",
                "source_id":       burst.burst_id,
                "privacy_tier":    burst.privacy_tier,
            })

        if rows:
            self.db.upsert_rows("chunks", rows)

        logger.debug(f"Mirrored {len(rows)} bursts to chunks")
        return len(rows)

    # ── Row builders ─────────────────────────────────────────────

    def _burst_to_row(self, burst: IMessageBurst) -> dict:
        return {
            "id":              burst.burst_id,
            "thread_id":       burst.thread_id,
            "thread_name":     burst.thread_name,
            "thread_type":     burst.thread_type,
            "burst_index":     burst.burst_index,
            "date_start":      burst.date_start,
            "date_end":        burst.date_end,
            "participants":    burst.participants,
            "dominant_sender": burst.dominant_sender,
            "text_combined":   burst.text_combined,
            "resource_links":  burst.resource_links,
            "privacy_tier":    burst.privacy_tier,
            "embedding":       None,
            "source_file":     _basename(burst.source_file),
        }

    def _message_to_row(self, msg: IMessageMessage, thread_id: str) -> dict:
        return {
            "id":              msg.message_id,
            "thread_id":       thread_id,
            "sender_name":     msg.sender_name,
            "sender_id":       msg.sender_id,
            "timestamp":       msg.timestamp.isoformat(),
            "text":            msg.text,
            "message_type":    msg.message_type,
            "reactions":       msg.reactions,
            "attachment":      msg.attachment,
            "attachment_type": msg.attachment_type,
            "has_text":        msg.has_text,
        }


# ─────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────

def _basename(path: str) -> str:
    from pathlib import Path
    return Path(path).name
