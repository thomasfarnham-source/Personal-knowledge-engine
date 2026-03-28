"""
Yahoo Mail Ingestor
=====================
Bridges the Yahoo Mail parser output (ParsedNote objects) to Supabase.

Writes to three tables:
  - email_conversations — structural metadata (participant set)
  - email_messages — per-email metadata (Message-ID, headers)
  - retrieval_units — burst content + embedding (unified retrieval)

Usage (as module):
    from pke.ingestion.yahoo_mail_ingestor import ingest_mbox
    report = ingest_mbox("/path/to/contact.mbox")

Usage (CLI):
    pke ingest-yahoo /path/to/contact.mbox
    pke ingest-yahoo /path/to/contact.mbox --dry-run
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pke.parsers.yahoo_mail_parser import (
    parse_emails,
    parse_mbox,
)

# ============================================================
# Conversation ID Generation
# ============================================================


def participant_hash(participants: list[str]) -> str:
    """
    Generate a stable hash from a sorted participant list.
    This defines the conversation — same participants = same
    conversation regardless of topic or time.
    """
    normalized = sorted(set(p.lower().strip() for p in participants))
    key = ",".join(normalized)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ============================================================
# Ingestion Report
# ============================================================


@dataclass
class IngestionReport:
    """Summary of what the ingestor did."""

    mbox_path: str = ""
    emails_parsed: int = 0
    conversations_created: int = 0
    conversations_existing: int = 0
    messages_upserted: int = 0
    messages_skipped: int = 0
    bursts_created: int = 0
    bursts_skipped: int = 0
    embeddings_generated: int = 0
    errors: list[str] = field(default_factory=list)

    def print_summary(self) -> None:
        """Print a human-readable summary."""
        print(f"\nIngestion Report: {self.mbox_path}")
        print(f"  Emails parsed:          {self.emails_parsed:,}")
        print(f"  Conversations created:  {self.conversations_created:,}")
        print(f"  Conversations existing: {self.conversations_existing:,}")
        print(f"  Messages upserted:      {self.messages_upserted:,}")
        print(f"  Messages skipped:       {self.messages_skipped:,}")
        print(f"  Bursts created:         {self.bursts_created:,}")
        print(f"  Bursts skipped:         {self.bursts_skipped:,}")
        print(f"  Embeddings generated:   {self.embeddings_generated:,}")
        if self.errors:
            print(f"  Errors:                 {len(self.errors)}")
            for err in self.errors[:5]:
                print(f"    - {err}")


# ============================================================
# Ingestor
# ============================================================


def ingest_mbox(
    mbox_path: str,
    supabase_client: Any,
    embedding_client: Any | None = None,
    owner_address: str = "thomas.farnham@yahoo.com",
    gap_threshold_hours: float = 4.0,
    dry_run: bool = False,
) -> IngestionReport:
    """
    Ingest a Yahoo Mail MBOX file into Supabase.

    Pipeline:
      1. Parse MBOX → ParsedNote objects (bursts)
      2. Also parse raw emails for metadata extraction
      3. Upsert conversations (by participant hash)
      4. Upsert email messages (by Message-ID)
      5. Upsert bursts into retrieval_units
      6. Generate embeddings for new retrieval units

    Args:
        mbox_path: Path to the MBOX file.
        supabase_client: SupabaseClient instance.
        embedding_client: EmbeddingClient for generating embeddings.
                         If None, embeddings are deferred.
        owner_address: Mailbox owner's email address.
        gap_threshold_hours: Time gap for burst segmentation.
        dry_run: If True, parse and report but don't write.

    Returns:
        IngestionReport summarizing what was done.
    """
    report = IngestionReport(mbox_path=mbox_path)

    # Step 1: Parse into bursts (ParsedNote objects)
    print(f"Parsing: {mbox_path}")
    notes = parse_mbox(mbox_path, owner_address, gap_threshold_hours)
    print(f"Parsed into {len(notes)} bursts.")

    # Step 2: Also parse raw emails for metadata
    emails = parse_emails(mbox_path, owner_address)
    report.emails_parsed = len(emails)
    print(f"Parsed {len(emails)} emails for metadata.")

    if dry_run:
        report.bursts_created = len(notes)
        report.messages_upserted = len(emails)
        print("\nDry run — no data written to Supabase.")
        report.print_summary()
        return report

    # Step 3: Upsert conversations
    print("\nUpserting conversations...")
    conversations_seen: dict[str, str] = {}  # hash → conversation UUID

    for note in notes:
        participants = note.participants or []
        if not participants:
            continue

        p_hash = participant_hash(participants)
        if p_hash in conversations_seen:
            continue

        # Check if conversation already exists
        existing = (
            supabase_client.client.table("email_conversations")
            .select("id")
            .eq("participant_hash", p_hash)
            .execute()
        )

        if existing.data:
            conversations_seen[p_hash] = existing.data[0]["id"]
            report.conversations_existing += 1
        else:
            # Create new conversation
            conv_data = {
                "participant_hash": p_hash,
                "participants": sorted(participants),
                "participant_count": len(participants),
                "first_message_at": note.created_at,
                "last_message_at": note.updated_at,
                "message_count": note.metadata.get("email_count", 0),
                "burst_count": 1,
            }
            result = supabase_client.client.table("email_conversations").insert(conv_data).execute()

            if result.data:
                conversations_seen[p_hash] = result.data[0]["id"]
                report.conversations_created += 1

    print(f"  {report.conversations_created} created, " f"{report.conversations_existing} existing")

    # Step 4: Upsert email messages
    print("Upserting email messages...")
    for email in emails:
        # Find conversation for this email
        p_hash = participant_hash(email.all_participants)
        conversation_id = conversations_seen.get(p_hash)

        msg_data = {
            "message_id": email.message_id,
            "conversation_id": conversation_id,
            "subject": email.subject[:500] if email.subject else None,
            "from_addr": email.from_addr,
            "from_name": email.from_name or None,
            "to_addrs": email.to_addrs,
            "cc_addrs": email.cc_addrs if email.cc_addrs else None,
            "date": email.date_iso or None,
            "direction": email.direction,
            "thread_root": email.thread_root or None,
            "in_reply_to": None,  # stored in thread_root logic
            "has_attachments": len(email.attachments) > 0,
            "source_file": str(Path(mbox_path).resolve()),
        }

        try:
            supabase_client.client.table("email_messages").upsert(
                msg_data, on_conflict="message_id"
            ).execute()
            report.messages_upserted += 1
        except Exception as e:
            report.messages_skipped += 1
            if len(report.errors) < 10:
                report.errors.append(f"Message {email.message_id[:40]}: {e}")

    print(f"  {report.messages_upserted} upserted, " f"{report.messages_skipped} skipped")

    # Step 5: Upsert bursts into retrieval_units
    print("Upserting retrieval units...")
    units_to_embed: list[dict[str, Any]] = []

    for note in notes:
        unit_data = {
            "source_type": "email",
            "source_id": note.id,
            "body": note.body,
            "title": note.title[:500] if note.title else None,
            "notebook": note.notebook,
            "created_at": note.created_at or None,
            "updated_at": note.updated_at or None,
            "participants": note.participants,
            "privacy_tier": note.privacy_tier or 3,
            "dominant_sender": note.dominant_sender,
            "thread_id": note.thread_id,
            "thread_type": note.thread_type,
            "metadata": note.metadata,
        }

        try:
            result = (
                supabase_client.client.table("retrieval_units")
                .upsert(
                    unit_data,
                    on_conflict="source_type,source_id",
                )
                .execute()
            )
            report.bursts_created += 1

            if result.data:
                units_to_embed.append(result.data[0])
        except Exception as e:
            report.bursts_skipped += 1
            if len(report.errors) < 10:
                report.errors.append(f"Burst {note.id[:40]}: {e}")

    print(f"  {report.bursts_created} created, " f"{report.bursts_skipped} skipped")

    # Step 6: Generate embeddings
    if embedding_client and units_to_embed:
        print("Generating embeddings...")
        for unit in units_to_embed:
            if unit.get("embedding"):
                continue
            try:
                embedding = embedding_client.generate(unit["body"])
                supabase_client.client.table("retrieval_units").update({"embedding": embedding}).eq(
                    "id", unit["id"]
                ).execute()
                report.embeddings_generated += 1

                if report.embeddings_generated % 50 == 0:
                    print(f"  {report.embeddings_generated} " f"embeddings generated...")
            except Exception as e:
                if len(report.errors) < 10:
                    report.errors.append(f"Embedding for {unit['source_id'][:40]}: {e}")

        print(f"  {report.embeddings_generated} embeddings generated")
    elif not embedding_client:
        print("No embedding client provided — " "embeddings deferred to backfill.")

    # Update conversation counts
    print("Updating conversation counts...")
    for p_hash, conv_id in conversations_seen.items():
        try:
            # Count messages for this conversation
            msg_count = (
                supabase_client.client.table("email_messages")
                .select("id", count="exact")
                .eq("conversation_id", conv_id)
                .execute()
            )

            update_data: dict[str, Any] = {}
            if msg_count.count is not None:
                update_data["message_count"] = msg_count.count

            if update_data:
                supabase_client.client.table("email_conversations").update(update_data).eq(
                    "id", conv_id
                ).execute()
        except Exception:
            pass  # Non-critical update

    report.print_summary()
    return report


# ============================================================
# CLI Entry Point
# ============================================================


def main() -> None:
    """CLI entry point for testing."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python yahoo_mail_ingestor.py " "<path_to_mbox> [--dry-run]")
        sys.exit(1)

    mbox_path = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        # Dry run doesn't need real clients
        report = IngestionReport(mbox_path=mbox_path)
        notes = parse_mbox(mbox_path)
        emails = parse_emails(mbox_path, "thomas.farnham@yahoo.com")

        report.emails_parsed = len(emails)
        report.bursts_created = len(notes)

        # Count unique conversations
        conv_hashes: set[str] = set()
        for note in notes:
            if note.participants:
                conv_hashes.add(participant_hash(note.participants))
        report.conversations_created = len(conv_hashes)

        print("\nDry run — no data written to Supabase.")
        report.print_summary()

        # Show conversation breakdown
        print(f"\n  Unique conversations: {len(conv_hashes)}")
        conv_counts: dict[str, dict[str, Any]] = {}
        for note in notes:
            if not note.participants:
                continue
            p_hash = participant_hash(note.participants)
            if p_hash not in conv_counts:
                conv_counts[p_hash] = {
                    "participants": note.participants,
                    "bursts": 0,
                    "type": note.thread_type,
                }
            conv_counts[p_hash]["bursts"] += 1

        for p_hash, info in sorted(
            conv_counts.items(),
            key=lambda x: -x[1]["bursts"],
        )[:15]:
            participants = ", ".join(p.split("@")[0] for p in info["participants"])
            print(f"    {info['bursts']:>4} bursts  " f"{info['type']:<10}  {participants}")
    else:
        # Real ingestion — needs clients
        print("Real ingestion requires SupabaseClient and " "EmbeddingClient.")
        print("Use: pke ingest-yahoo <mbox_path> " "(via CLI with configured clients)")
        sys.exit(1)


if __name__ == "__main__":
    main()
