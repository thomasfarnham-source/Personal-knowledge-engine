"""
pke/parsers/imessage_parser.py

Parser for iMessage thread exports from iMazing CSV format.

═══════════════════════════════════════════════════════════════════
WHAT THIS FILE DOES
═══════════════════════════════════════════════════════════════════

Reads one or more iMazing CSV exports and produces:

    1. A list of IMessageThread objects — one per CSV file
    2. A list of IMessageBurst objects — conversation bursts,
       the primary unit of ingestion into the PKE pipeline
    3. ParsedNote contract output — one ParsedNote per burst,
       ready for the PKE ingestion pipeline

The parser is intentionally isolated from the database. It reads
CSV files and produces structured Python objects. It never calls
Supabase or any external service.

═══════════════════════════════════════════════════════════════════
IMESSAGE CSV FORMAT (iMazing export)
═══════════════════════════════════════════════════════════════════

Columns (17 total):
    Chat Session    — thread name (participants joined by " & ")
    Message Date    — ISO datetime "YYYY-MM-DD HH:MM:SS"
    Delivered Date  — ISO datetime or empty
    Read Date       — ISO datetime or empty
    Edited Date     — ISO datetime or empty
    Deleted Date    — ISO datetime or empty
    Service         — "SMS" or empty
    Type            — "Incoming" | "Outgoing" | "Notification"
    Sender ID       — phone number e.g. "+16467327168" or empty
    Sender Name     — display name or empty
    Status          — "Read" | "Delivered" | empty
    Replying to     — empty in current corpus
    Subject         — empty in current corpus
    Text            — message content (may be empty for attachments)
    Reactions       — reaction description or empty
    Attachment      — attachment filename or empty
    Attachment type — MIME type or empty

Sender resolution rules:
    Type == "Outgoing" and Sender Name == "" → SELF (Thomas)
    Type == "Incoming" → use Sender Name
    Type == "Notification" → skip

═══════════════════════════════════════════════════════════════════
CONVERSATION BURST STRATEGY
═══════════════════════════════════════════════════════════════════

Messages are grouped into conversation bursts — semantically
coherent conversational episodes. A new burst begins when the
gap between consecutive messages exceeds BURST_GAP_HOURS (4h).

Rationale:
    - A single message ("ok sounds good") is too thin for retrieval
    - A full day's conversation may span multiple distinct topics
    - 4 hours represents a natural break between conversational sessions
    - Preserves conversational context for semantic retrieval

Bursts with no text content (all attachments, no prose) are
excluded from ingestion — they produce no useful embedding.

═══════════════════════════════════════════════════════════════════
PARSEDNOTE CONTRACT OUTPUT
═══════════════════════════════════════════════════════════════════

Each burst produces one ParsedNote:

    id              — burst UUID
    title           — "{thread_name} — {date}"
    body            — combined text of all messages in burst
    notebook        — "iMessage" | "iMessage-bilateral"
    tags            — []
    created_at      — burst start timestamp (ISO)
    updated_at      — burst start timestamp (ISO)
    metadata        — {
                        thread_id, thread_type, thread_name,
                        participants, dominant_sender,
                        message_count, burst_index
                      }
    source_file     — path to source CSV
    resource_links  — attachment filenames in burst
    source_type     — "imessage"
    participants    — list of display names in burst
    dominant_sender — sender with most messages in burst
    thread_id       — UUID of source thread
    thread_type     — "group" | "bilateral"
    person_ids      — None (reserved for entity layer)

═══════════════════════════════════════════════════════════════════
RELATIONSHIP TO OTHER FILES
═══════════════════════════════════════════════════════════════════

    pke/parsers/joplin_sync_parser.py — canonical parser pattern
    pke/ingestion/orchestrator.py     — consumes ParsedNote output
    pke/api/models/query.py           — QueryResult shape (retrieval)
"""

import csv
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────

# Gap threshold for burst detection.
# Messages more than this many hours apart start a new burst.
BURST_GAP_HOURS: int = 4

# Display name used for outgoing messages with no Sender Name.
SELF_NAME: str = "Thomas"

# Thread type classifications
THREAD_TYPE_GROUP: str = "group"
THREAD_TYPE_BILATERAL: str = "bilateral"

# Notebook names for PKE ingestion
NOTEBOOK_GROUP: str = "iMessage"
NOTEBOOK_BILATERAL: str = "iMessage-bilateral"

# Minimum text length for a burst to be worth ingesting.
# Bursts below this threshold are attachment-only and skipped.
MIN_BURST_TEXT_LENGTH: int = 20


# ─────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────


@dataclass
class IMessageThread:
    """
    Represents a single iMessage conversation thread.
    Derived from the CSV Chat Session field and participant list.
    """

    thread_id: str  # deterministic UUID from thread name
    thread_name: str  # raw Chat Session value
    thread_type: str  # "group" | "bilateral"
    participants: list[str]  # display names of all participants
    source_file: str  # absolute path to source CSV
    date_start: str  # ISO timestamp of first message
    date_end: str  # ISO timestamp of last message
    message_count: int  # total messages in thread


@dataclass
class IMessageMessage:
    """
    Represents a single message within a thread.
    Attachment-only messages (no text) are preserved but flagged.
    """

    message_id: str  # deterministic ID from timestamp + sender
    thread_id: str
    sender_name: str  # resolved display name (SELF_NAME for outgoing)
    sender_id: str  # phone number or empty
    timestamp: datetime
    text: str  # cleaned message text (may be empty)
    message_type: str  # "Incoming" | "Outgoing"
    reactions: str  # raw reaction string or empty
    attachment: str  # attachment filename or empty
    attachment_type: str  # MIME type or empty
    has_text: bool  # True if text is non-empty after cleaning


@dataclass
class IMessageBurst:
    """
    A conversation burst — the primary unit of PKE ingestion.

    Groups messages within a 4-hour window into a single
    semantically coherent unit for embedding and retrieval.
    """

    burst_id: str  # deterministic UUID
    thread_id: str
    thread_name: str
    thread_type: str
    burst_index: int  # sequential within thread
    date_start: str  # ISO timestamp of first message
    date_end: str  # ISO timestamp of last message
    messages: list[IMessageMessage] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    dominant_sender: str = ""  # sender with most messages
    text_combined: str = ""  # full text for embedding
    resource_links: list[str] = field(default_factory=list)
    source_file: str = ""

    @property
    def has_content(self) -> bool:
        """
        True if burst has real text content worth embedding.
        Attachment-only bursts (no prose text from any message)
        are excluded — their combined text contains only attachment
        references which produce no useful semantic embedding.
        """
        return any(msg.has_text for msg in self.messages)


# ─────────────────────────────────────────────────────────────────
# PARSEDNOTE CONTRACT OUTPUT
# ─────────────────────────────────────────────────────────────────


def burst_to_parsed_note(burst: IMessageBurst) -> dict:
    """
    Convert an IMessageBurst to a ParsedNote contract dict.

    The ParsedNote contract is the standard output format for all
    PKE parsers. This function bridges the iMessage domain model
    to the shared ingestion pipeline contract.

    See Section 4 of ARCHITECTURE.md for the full contract spec.
    """
    notebook = NOTEBOOK_GROUP if burst.thread_type == THREAD_TYPE_GROUP else NOTEBOOK_BILATERAL

    # Format title as "Thread Name — YYYY-MM-DD"
    date_label = burst.date_start[:10] if burst.date_start else ""
    title = f"{burst.thread_name} — {date_label}"

    return {
        # ── Core ParsedNote fields ───────────────────────────────
        "id": burst.burst_id,
        "title": title,
        "body": burst.text_combined,
        "notebook": notebook,
        "tags": [],
        "created_at": burst.date_start,
        "updated_at": burst.date_start,
        "metadata": {
            "thread_id": burst.thread_id,
            "thread_type": burst.thread_type,
            "thread_name": burst.thread_name,
            "participants": burst.participants,
            "dominant_sender": burst.dominant_sender,
            "message_count": len(burst.messages),
            "burst_index": burst.burst_index,
        },
        "source_file": burst.source_file,
        "resource_links": burst.resource_links,
        # ── Multi-source extension fields (Section 4) ────────────
        "source_type": "imessage",
        "participants": burst.participants,
        "dominant_sender": burst.dominant_sender,
        "thread_id": burst.thread_id,
        "thread_type": burst.thread_type,
        # ── Entity layer — reserved, not populated in v1 ─────────
        "person_ids": None,
    }


# ─────────────────────────────────────────────────────────────────
# PARSING UTILITIES
# ─────────────────────────────────────────────────────────────────


def _make_id(seed: str) -> str:
    """
    Generate a deterministic ID from a seed string.
    Uses SHA-256 truncated to 32 hex chars — collision-resistant
    and stable across runs (determinism requirement).
    """
    return hashlib.sha256(seed.encode()).hexdigest()[:32]


def _parse_timestamp(value: str) -> Optional[datetime]:
    """
    Parse an iMazing timestamp string to a datetime object.
    Format: "YYYY-MM-DD HH:MM:SS"
    Returns None if the value is empty or unparseable.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        logger.warning(f"Unparseable timestamp: {value!r}")
        return None


def _clean_text(text: str) -> str:
    """
    Clean message text for ingestion.

    - Strip leading/trailing whitespace
    - Normalise internal whitespace (collapse multiple newlines)
    - Remove null bytes
    - Strip HTML tags if present (Joplin artefact defence)
    - Collapse multiple spaces left by HTML stripping

    Does NOT strip URLs — they may be the entire content of a message
    and carry semantic signal (the group shares links constantly).
    """
    if not text:
        return ""

    # Remove null bytes
    text = text.replace("\x00", "")

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Collapse multiple spaces left by HTML stripping
    text = re.sub(r" {2,}", " ", text)

    # Normalise whitespace — collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _resolve_sender(row: dict) -> str:
    """
    Resolve the display name of the message sender.

    Rules:
        Type == "Outgoing" and Sender Name == "" → SELF_NAME
        Type == "Incoming" → Sender Name (may be empty for unknown)
        Anything else → Sender Name or "Unknown"
    """
    if row.get("Type") == "Outgoing" and not row.get("Sender Name"):
        return SELF_NAME
    return row.get("Sender Name") or "Unknown"


def _classify_thread(participants: list[str]) -> str:
    """
    Classify thread type based on participant count.
    2 participants (including self) → bilateral
    3+ participants → group
    """
    # Filter out SELF_NAME for count — we care about counterparties
    counterparties = [p for p in participants if p != SELF_NAME]
    return THREAD_TYPE_BILATERAL if len(counterparties) == 1 else THREAD_TYPE_GROUP


def _build_burst_text(messages: list[IMessageMessage]) -> str:
    """
    Combine message texts into a single burst text for embedding.

    Format: "{Sender}: {text}\n\n" for each message with text.
    Messages without text (attachment-only) contribute their
    attachment filename as a brief reference.
    """
    parts = []
    for msg in messages:
        if msg.has_text:
            parts.append(f"{msg.sender_name}: {msg.text}")
        elif msg.attachment:
            # Note attachment presence without full filename
            ext = Path(msg.attachment).suffix.lower()
            parts.append(f"{msg.sender_name}: [attachment{ext}]")

    return "\n\n".join(parts)


def _dominant_sender(messages: list[IMessageMessage]) -> str:
    """
    Return the display name of the sender with the most messages
    in this burst. Used for Group Voice channel retrieval filtering.
    """
    from collections import Counter

    counts = Counter(msg.sender_name for msg in messages if msg.has_text)
    if not counts:
        return ""
    return counts.most_common(1)[0][0]


# ─────────────────────────────────────────────────────────────────
# CORE PARSER
# ─────────────────────────────────────────────────────────────────


def parse_imessage_csv(csv_path: str) -> tuple[IMessageThread, list[IMessageBurst]]:
    """
    Parse a single iMazing CSV export into a thread and its bursts.

    Args:
        csv_path: absolute path to the iMazing CSV export file

    Returns:
        (IMessageThread, list[IMessageBurst])
        The thread metadata and ordered list of conversation bursts.

    Raises:
        FileNotFoundError: if csv_path does not exist
        ValueError: if the CSV has unexpected structure

    Notes:
        - Notification rows are skipped
        - Attachment-only messages are preserved but flagged
        - Bursts with no text content are excluded from output
        - All timestamps are stored as ISO strings for consistency
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    logger.info(f"Parsing iMessage CSV: {path.name}")

    # ── Pass 1: Load and parse all messages ──────────────────────
    raw_messages: list[IMessageMessage] = []
    thread_name: str = ""
    all_senders: set[str] = set()

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader):
            # Skip notifications — system messages, not conversations
            if row.get("Type") == "Notification":
                logger.debug(f"Skipping notification row {i}")
                continue

            # Skip rows with no timestamp — malformed
            timestamp = _parse_timestamp(row.get("Message Date", ""))
            if timestamp is None:
                logger.warning(f"Skipping row {i} — no valid timestamp")
                continue

            # Capture thread name from first row
            if not thread_name:
                thread_name = row.get("Chat Session", "Unknown Thread")

            sender_name = _resolve_sender(row)
            all_senders.add(sender_name)

            text = _clean_text(row.get("Text", ""))
            attachment = row.get("Attachment", "").strip()

            # Generate deterministic message ID
            message_id = _make_id(f"{csv_path}:{row.get('Message Date', '')}:{sender_name}:{i}")

            # Thread ID is deterministic from the CSV path
            thread_id = _make_id(csv_path)

            raw_messages.append(
                IMessageMessage(
                    message_id=message_id,
                    thread_id=thread_id,
                    sender_name=sender_name,
                    sender_id=row.get("Sender ID", ""),
                    timestamp=timestamp,
                    text=text,
                    message_type=row.get("Type", ""),
                    reactions=row.get("Reactions", ""),
                    attachment=attachment,
                    attachment_type=row.get("Attachment type", ""),
                    has_text=bool(text),
                )
            )

    if not raw_messages:
        logger.warning(f"No messages parsed from {csv_path}")
        return _empty_thread(csv_path, thread_name), []

    # Sort by timestamp — should already be sorted but enforce it
    raw_messages.sort(key=lambda m: m.timestamp)

    logger.info(f"Loaded {len(raw_messages)} messages from {path.name}")

    # ── Pass 2: Group into conversation bursts ───────────────────
    bursts: list[IMessageBurst] = []
    current_burst_messages: list[IMessageMessage] = [raw_messages[0]]
    thread_id = _make_id(csv_path)
    burst_index = 0

    for msg in raw_messages[1:]:
        prev = current_burst_messages[-1]
        gap = msg.timestamp - prev.timestamp

        if gap > timedelta(hours=BURST_GAP_HOURS):
            # Gap exceeds threshold — close current burst, start new one
            burst = _build_burst(
                messages=current_burst_messages,
                thread_id=thread_id,
                thread_name=thread_name,
                burst_index=burst_index,
                source_file=csv_path,
            )
            if burst.has_content:
                bursts.append(burst)
                burst_index += 1
            else:
                logger.debug(f"Skipping empty burst at {current_burst_messages[0].timestamp}")
            current_burst_messages = [msg]
        else:
            current_burst_messages.append(msg)

    # Close the final burst
    if current_burst_messages:
        burst = _build_burst(
            messages=current_burst_messages,
            thread_id=thread_id,
            thread_name=thread_name,
            burst_index=burst_index,
            source_file=csv_path,
        )
        if burst.has_content:
            bursts.append(burst)

    logger.info(f"Produced {len(bursts)} bursts from {path.name}")

    # ── Pass 3: Build thread metadata ────────────────────────────
    participants = sorted(all_senders)
    thread_type = _classify_thread(participants)

    thread = IMessageThread(
        thread_id=thread_id,
        thread_name=thread_name,
        thread_type=thread_type,
        participants=participants,
        source_file=csv_path,
        date_start=raw_messages[0].timestamp.isoformat(),
        date_end=raw_messages[-1].timestamp.isoformat(),
        message_count=len(raw_messages),
    )

    # Backfill thread_type onto bursts (known after participant analysis)
    for burst in bursts:
        burst.thread_type = thread_type

    return thread, bursts


def _build_burst(
    messages: list[IMessageMessage],
    thread_id: str,
    thread_name: str,
    burst_index: int,
    source_file: str,
) -> IMessageBurst:
    """
    Construct an IMessageBurst from a list of consecutive messages.
    """
    date_start = messages[0].timestamp.isoformat()
    date_end = messages[-1].timestamp.isoformat()

    # Deterministic burst ID from thread + start timestamp + index
    burst_id = _make_id(f"{thread_id}:{date_start}:{burst_index}")

    participants = sorted(set(m.sender_name for m in messages))
    text_combined = _build_burst_text(messages)
    dom_sender = _dominant_sender(messages)
    resource_links = [m.attachment for m in messages if m.attachment]

    return IMessageBurst(
        burst_id=burst_id,
        thread_id=thread_id,
        thread_name=thread_name,
        thread_type=THREAD_TYPE_GROUP,  # overwritten after participant analysis
        burst_index=burst_index,
        date_start=date_start,
        date_end=date_end,
        messages=messages,
        participants=participants,
        dominant_sender=dom_sender,
        text_combined=text_combined,
        resource_links=resource_links,
        source_file=source_file,
    )


def _empty_thread(csv_path: str, thread_name: str) -> IMessageThread:
    """Return an empty thread record for a CSV with no parseable messages."""
    return IMessageThread(
        thread_id=_make_id(csv_path),
        thread_name=thread_name or "Unknown",
        thread_type=THREAD_TYPE_GROUP,
        participants=[],
        source_file=csv_path,
        date_start="",
        date_end="",
        message_count=0,
    )


# ─────────────────────────────────────────────────────────────────
# MULTI-FILE ENTRY POINT
# ─────────────────────────────────────────────────────────────────


def parse_imessage_exports(export_dir: str) -> tuple[list[IMessageThread], list[dict]]:
    """
    Parse all iMazing CSV exports in a directory.

    Args:
        export_dir: path to folder containing iMazing CSV exports

    Returns:
        (threads, parsed_notes)
        threads      — list of IMessageThread objects
        parsed_notes — list of ParsedNote dicts ready for ingestion

    Notes:
        - Processes all .csv files in the directory
        - Each CSV becomes one thread
        - Returns ParsedNote contract dicts for ingestion pipeline
    """
    export_path = Path(export_dir)
    if not export_path.exists():
        raise FileNotFoundError(f"Export directory not found: {export_dir}")

    csv_files = sorted(export_path.glob("*.csv"))
    if not csv_files:
        logger.warning(f"No CSV files found in {export_dir}")
        return [], []

    logger.info(f"Found {len(csv_files)} CSV file(s) in {export_dir}")

    all_threads: list[IMessageThread] = []
    all_parsed_notes: list[dict] = []

    for csv_file in csv_files:
        try:
            thread, bursts = parse_imessage_csv(str(csv_file))
            all_threads.append(thread)

            for burst in bursts:
                all_parsed_notes.append(burst_to_parsed_note(burst))

            logger.info(
                f"  {csv_file.name}: {thread.message_count} messages → " f"{len(bursts)} bursts"
            )
        except Exception as e:
            logger.error(f"Failed to parse {csv_file.name}: {e}")
            raise

    logger.info(
        f"Total: {len(all_threads)} thread(s), " f"{len(all_parsed_notes)} burst(s) → parsed notes"
    )

    return all_threads, all_parsed_notes
