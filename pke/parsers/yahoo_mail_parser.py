"""
Yahoo Mail Parser (Thread-Aware)
==================================
Converts per-contact MBOX files into ParsedNote contract objects
for the PKE ingestion pipeline.

Design:
  1. Parse all emails from MBOX
  2. Group into threads by References/In-Reply-To chain
  3. Segment threads into bursts at time gaps > threshold (default 4h)
  4. For each burst, use the last email's full body as the record
     (it contains the complete conversation in quoted text)
  5. One ParsedNote per burst — the burst is the retrieval unit

Key insight: in email threads, the most recent reply contains the
full conversation history in its quoted content. Rather than stripping
quotes and reassembling fragments, we use the last email per burst as
the complete conversational snapshot. This preserves all participants'
contributions and the natural flow of the discussion.

Quote stripping (stripped_body) is still computed per-email but used
only to detect branch divergence — when earlier emails in a burst
contain content NOT present in the latest email.

This follows the same model as the iMessage parser:
  emails → threads → bursts → ParsedNote objects

Usage (as module):
    from pke.parsers.yahoo_mail_parser import parse_mbox
    notes = parse_mbox("/path/to/contact.mbox")

Usage (CLI test):
    python -m pke.parsers.yahoo_mail_parser /path/to/contact.mbox
"""

import mailbox
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from typing import Any

from pke.parsers.contact_identity_map import (
    normalize_address,
    normalize_participants,
)

# ============================================================
# HTML Stripping
# ============================================================


class _HTMLTextExtractor(HTMLParser):
    """Extract visible text from HTML, stripping tags and scripts."""

    def __init__(self) -> None:
        super().__init__()
        self._output: StringIO = StringIO()
        self._skip: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "head"):
            self._skip = True
        elif tag in (
            "br",
            "p",
            "div",
            "tr",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ):
            self._output.write("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "head"):
            self._skip = False
        elif tag in (
            "p",
            "div",
            "tr",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ):
            self._output.write("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._output.write(data)

    def get_text(self) -> str:
        return self._output.getvalue()


def strip_html(html: str) -> str:
    """Strip HTML tags and return plain text."""
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", "", html)
    text = extractor.get_text()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ============================================================
# Quote / Signature / Forward Stripping
# ============================================================

# "On [date], [person] wrote:" attribution lines
ATTRIBUTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^On .{10,100}wrote:\s*$", re.MULTILINE),
    re.compile(r"^On .{10,100}<[^>]+>\s*wrote:\s*$", re.MULTILINE),
]

# Forwarded message delimiters
FORWARD_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"-{5,}\s*Forwarded message\s*-{5,}", re.IGNORECASE),
    re.compile(r"-{5,}\s*Original Message\s*-{5,}", re.IGNORECASE),
]

# BlackBerry / Yahoo / Outlook original message headers
ORIGINAL_MSG_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"-{3,}Original Message-{3,}", re.IGNORECASE),
    re.compile(r"^-{3}\s*On .{10,100}wrote:\s*$", re.MULTILINE),
    re.compile(
        r"^-{3,}\s*On\s+\w{3},\s+\d{1,2}/\d{1,2}/\d{2,4},\s+",
        re.MULTILINE,
    ),
]

# Signature patterns
SIGNATURE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"^Sent from my (?:iPhone|iPad|Tricorder|BlackBerry).*$",
        re.MULTILINE,
    ),
    re.compile(r"^Sent via BlackBerry.*$", re.MULTILINE),
    re.compile(r"^Get Outlook for (?:iOS|Android).*$", re.MULTILINE),
    re.compile(r"^-- \n.*", re.DOTALL),
    re.compile(
        r"No virus found in this (?:incoming|outgoing) message\..*?$",
        re.MULTILINE | re.DOTALL,
    ),
    re.compile(r"^Checked by AVG.*$", re.MULTILINE),
    re.compile(r"^M: \d{3}\.\d{3}\.\d{4}\s*$", re.MULTILINE),
]


def strip_quoted_content(body: str) -> str:
    """
    Strip quoted/forwarded content from an email body.
    Returns only the new content the sender actually wrote.
    """
    if not body:
        return ""

    lines = body.split("\n")
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Stop at forwarded message delimiters
        hit_forward = False
        for pattern in FORWARD_PATTERNS:
            if pattern.search(line):
                hit_forward = True
                break
        if hit_forward:
            break

        # Stop at "-----Original Message-----" style delimiters
        hit_original = False
        for pattern in ORIGINAL_MSG_PATTERNS:
            if pattern.search(line):
                hit_original = True
                break
        if hit_original:
            break

        # Stop at attribution lines ("On ... wrote:")
        hit_attribution = False
        for pattern in ATTRIBUTION_PATTERNS:
            if pattern.match(line):
                hit_attribution = True
                break
        if hit_attribution:
            break

        # Skip angle-bracket quoted lines
        if stripped.startswith(">"):
            continue

        new_lines.append(line)

    result = "\n".join(new_lines)

    # Strip signatures
    for pattern in SIGNATURE_PATTERNS:
        result = pattern.sub("", result)

    # Collapse whitespace
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = result.strip()

    return result


# ============================================================
# Header Decoding
# ============================================================


def decode_header_value(raw: str | None) -> str:
    """Decode an RFC2047-encoded header value."""
    if not raw:
        return ""
    try:
        parts = decode_header(raw)
        decoded = ""
        for part, encoding in parts:
            if isinstance(part, bytes):
                decoded += part.decode(encoding or "utf-8", errors="replace")
            else:
                decoded += part
        return decoded
    except Exception:
        return str(raw)


def extract_email_addresses(msg: mailbox.mboxMessage, header_name: str) -> list[str]:
    """Extract email addresses from a header field."""
    raw_values = msg.get_all(header_name, [])
    if not raw_values:
        return []
    decoded = [decode_header_value(v) for v in raw_values]
    pairs = getaddresses(decoded)
    return [addr.lower() for _, addr in pairs if addr]


def extract_display_name(msg: mailbox.mboxMessage, header_name: str) -> str:
    """Extract the display name from a header field."""
    raw_values = msg.get_all(header_name, [])
    if not raw_values:
        return ""
    decoded = [decode_header_value(v) for v in raw_values]
    pairs = getaddresses(decoded)
    for name, addr in pairs:
        if name:
            return name
    return ""


def parse_date_dt(msg: mailbox.mboxMessage) -> datetime | None:
    """Parse date header to datetime object."""
    date_str = msg.get("Date", "")
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def parse_date_iso(msg: mailbox.mboxMessage) -> str:
    """Parse date header to ISO string."""
    dt = parse_date_dt(msg)
    return dt.isoformat() if dt else ""


def extract_body(msg: mailbox.mboxMessage) -> str:
    """
    Extract the message body, preferring plain text over HTML.
    Does NOT strip quotes — that happens at the thread assembly stage.
    """
    plain_body: str | None = None
    html_body: str | None = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = part.get_content_disposition()
            if disposition == "attachment":
                continue
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
            if content_type == "text/plain" and plain_body is None:
                plain_body = text
            elif content_type == "text/html" and html_body is None:
                html_body = text
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            charset = msg.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                html_body = text
            else:
                plain_body = text

    if plain_body:
        return plain_body
    elif html_body:
        return strip_html(html_body)
    else:
        return ""


def extract_attachment_metadata(
    msg: mailbox.mboxMessage,
) -> list[dict[str, Any]]:
    """Extract metadata for attachments (not content)."""
    attachments: list[dict[str, Any]] = []
    if not msg.is_multipart():
        return attachments
    for part in msg.walk():
        disposition = part.get_content_disposition()
        if disposition == "attachment" or (disposition == "inline" and part.get_filename()):
            payload = part.get_payload(decode=True)
            attachments.append(
                {
                    "filename": part.get_filename() or "unknown",
                    "content_type": part.get_content_type(),
                    "size": len(payload) if payload else 0,
                }
            )
    return attachments


# ============================================================
# Thread and Burst Assembly
# ============================================================


@dataclass
class EmailMessage:
    """Intermediate representation of a single parsed email."""

    message_id: str
    subject: str
    date: datetime | None
    date_iso: str
    from_addr: str
    from_name: str
    to_addrs: list[str]
    cc_addrs: list[str]
    all_participants: list[str]
    raw_body: str
    stripped_body: str
    thread_root: str
    direction: str
    attachments: list[dict[str, Any]]


def get_thread_root(msg: mailbox.mboxMessage) -> str:
    """
    Get the thread root Message-ID from References header.
    First ID in References is the thread root.
    Falls back to In-Reply-To, then to this message's own ID.
    """
    references = msg.get("References", "")
    if references:
        ref_ids = re.findall(r"<[^>]+>", references)
        if ref_ids:
            return ref_ids[0]
    in_reply_to = msg.get("In-Reply-To", "")
    if in_reply_to:
        ref_ids = re.findall(r"<[^>]+>", in_reply_to)
        if ref_ids:
            return ref_ids[0]
    return msg.get("Message-ID", f"<standalone-{id(msg)}>")


def determine_direction(from_addr: str, owner_address: str) -> str:
    """Determine if sent or received by the owner."""
    if owner_address.lower() in from_addr.lower():
        return "sent"
    return "received"


def parse_emails(mbox_path: str, owner_address: str) -> list[EmailMessage]:
    """Parse all emails from MBOX into EmailMessage objects."""
    mbox = mailbox.mbox(mbox_path)
    emails: list[EmailMessage] = []

    for msg in mbox:
        message_id = msg.get("Message-ID", "")
        if not message_id:
            date = msg.get("Date", "")
            subject = msg.get("Subject", "")
            from_hdr = msg.get("From", "")
            message_id = f"<synthetic-{hash(date + subject + from_hdr)}>"

        subject = decode_header_value(msg.get("Subject", ""))
        if not subject:
            subject = "(no subject)"

        raw_body = extract_body(msg)
        if not raw_body:
            continue

        stripped_body = strip_quoted_content(raw_body)

        from_addrs = extract_email_addresses(msg, "From")
        from_addr = from_addrs[0] if from_addrs else ""
        from_name = extract_display_name(msg, "From")
        to_addrs = extract_email_addresses(msg, "To")
        cc_addrs = extract_email_addresses(msg, "Cc")

        # Normalize all addresses through identity map
        all_participants = normalize_participants(from_addrs + to_addrs + cc_addrs)
        from_addr_normalized = normalize_address(from_addr)

        emails.append(
            EmailMessage(
                message_id=message_id,
                subject=subject,
                date=parse_date_dt(msg),
                date_iso=parse_date_iso(msg),
                from_addr=from_addr_normalized,
                from_name=from_name,
                to_addrs=to_addrs,
                cc_addrs=cc_addrs,
                all_participants=all_participants,
                raw_body=raw_body,
                stripped_body=stripped_body,
                thread_root=get_thread_root(msg),
                direction=determine_direction(from_addr, owner_address),
                attachments=extract_attachment_metadata(msg),
            )
        )

    return emails


def group_into_threads(
    emails: list[EmailMessage],
) -> dict[str, list[EmailMessage]]:
    """Group emails by thread root, sorted chronologically."""
    threads: dict[str, list[EmailMessage]] = {}
    for email in emails:
        root = email.thread_root
        if root not in threads:
            threads[root] = []
        threads[root].append(email)

    for root in threads:
        threads[root].sort(key=lambda e: e.date or datetime.min.replace(tzinfo=timezone.utc))

    return threads


def segment_into_bursts(
    thread: list[EmailMessage],
    gap_threshold_hours: float = 4.0,
) -> list[list[EmailMessage]]:
    """
    Split a thread into bursts at time gaps exceeding the threshold.
    Same concept as iMessage burst segmentation.
    """
    if not thread:
        return []
    if len(thread) == 1:
        return [thread]

    bursts: list[list[EmailMessage]] = []
    current_burst: list[EmailMessage] = [thread[0]]

    for i in range(1, len(thread)):
        prev_date = thread[i - 1].date
        curr_date = thread[i].date

        if prev_date and curr_date:
            gap_hours = (curr_date - prev_date).total_seconds() / 3600
            if gap_hours > gap_threshold_hours:
                bursts.append(current_burst)
                current_burst = []

        current_burst.append(thread[i])

    if current_burst:
        bursts.append(current_burst)

    return bursts


def clean_body_signatures(body: str) -> str:
    """
    Light cleanup of email body — strip signatures and device tags
    but preserve quoted conversation content.
    """
    if not body:
        return ""

    # Strip signatures
    for pattern in SIGNATURE_PATTERNS:
        body = pattern.sub("", body)

    # Collapse excessive whitespace
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def assemble_burst_body(burst: list[EmailMessage]) -> str:
    """
    Assemble a burst's body text.

    Strategy: use the LAST email in the burst as the primary body.
    In email threads, the most recent reply contains the full
    conversation history in its quoted text — it IS the complete
    record of the conversation up to that point.

    For single-email bursts, that email's full body is used.

    For multi-email bursts, the last email's body is the primary
    content. If earlier emails in the burst contain content NOT
    present in the last email (e.g. they were on a different
    branch of the thread), those are prepended.
    """
    if not burst:
        return ""

    if len(burst) == 1:
        return clean_body_signatures(burst[0].raw_body)

    # Use the last email as the primary body — it contains
    # the full conversation thread in its quoted content
    last_body = clean_body_signatures(burst[-1].raw_body)

    # Check if earlier emails in the burst have unique content
    # not present in the last email (different reply branches)
    extra_parts: list[str] = []
    for email in burst[:-1]:
        stripped = email.stripped_body
        if not stripped:
            continue
        # If this email's new content doesn't appear in the
        # last email's body, it's from a different branch
        if stripped[:100] not in last_body:
            date_str = ""
            if email.date:
                date_str = email.date.strftime("%Y-%m-%d %H:%M")
            sender = email.from_name or email.from_addr
            if " " in sender and "@" not in sender:
                sender = sender.split()[0]
            extra_parts.append(f"[{date_str} {sender}]: {stripped}")

    if extra_parts:
        extra = "\n\n".join(extra_parts)
        return f"{extra}\n\n---\n\n{last_body}"
    else:
        return last_body


# ============================================================
# ParsedNote Contract
# ============================================================


@dataclass
class ParsedNote:
    """
    ParsedNote contract — matches ARCHITECTURE.md Section 4.
    One ParsedNote per burst (not per email).
    """

    id: str
    title: str
    body: str
    notebook: str
    tags: list[str]
    created_at: str
    updated_at: str
    metadata: dict[str, Any]
    source_file: str
    resource_links: list[str]

    # Multi-source extension fields
    source_type: str | None = "email"
    participants: list[str] | None = None
    dominant_sender: str | None = None
    thread_id: str | None = None
    thread_type: str | None = None
    privacy_tier: int | None = 3
    person_ids: list[str] | None = None


# ============================================================
# Main Parser
# ============================================================


def parse_mbox(
    mbox_path: str,
    owner_address: str = "thomas.farnham@yahoo.com",
    gap_threshold_hours: float = 4.0,
) -> list[ParsedNote]:
    """
    Parse an MBOX file into ParsedNote objects.

    Pipeline:
      1. Parse all emails → EmailMessage objects
      2. Strip quoted content (done per-email in step 1)
      3. Group into threads by References chain
      4. Segment threads into bursts at time gaps
      5. Assemble burst body from stripped contributions
      6. One ParsedNote per burst

    Args:
        mbox_path: Path to the MBOX file.
        owner_address: Mailbox owner's email, for direction detection.
        gap_threshold_hours: Time gap to split threads into bursts.

    Returns:
        List of ParsedNote objects, one per burst.
    """
    source_file = str(Path(mbox_path).resolve())

    # Step 1: Parse all emails
    emails = parse_emails(mbox_path, owner_address)

    # Step 2: Group into threads
    threads = group_into_threads(emails)

    # Steps 3-5: Segment and assemble
    notes: list[ParsedNote] = []

    for thread_root, thread_emails in threads.items():
        bursts = segment_into_bursts(thread_emails, gap_threshold_hours)

        for burst_index, burst in enumerate(bursts):
            body = assemble_burst_body(burst)
            if not body:
                continue

            subject = burst[0].subject
            first_date = burst[0].date_iso
            last_date = burst[-1].date_iso

            # Collect participants (already normalized per-email)
            all_participants: set[str] = set()
            for email in burst:
                all_participants.update(email.all_participants)

            # Dominant sender (already normalized)
            sender_counts: dict[str, int] = {}
            for email in burst:
                addr = email.from_addr
                sender_counts[addr] = sender_counts.get(addr, 0) + 1
            dominant_sender = (
                max(
                    sender_counts,
                    key=sender_counts.get,  # type: ignore[arg-type]
                )
                if sender_counts
                else None
            )

            # Thread type
            thread_type = "bilateral" if len(all_participants) <= 2 else "group"

            # Burst ID and metadata
            burst_id = f"{thread_root}::burst-{burst_index}"
            message_ids = [e.message_id for e in burst]

            all_attachments: list[dict[str, Any]] = []
            for email in burst:
                all_attachments.extend(email.attachments)

            metadata: dict[str, Any] = {
                "message_ids": message_ids,
                "thread_root": thread_root,
                "burst_index": burst_index,
                "email_count": len(burst),
                "first_date": first_date,
                "last_date": last_date,
            }
            if all_attachments:
                metadata["attachments"] = all_attachments

            note = ParsedNote(
                id=burst_id,
                title=subject,
                body=body,
                notebook="yahoo-mail",
                tags=[],
                created_at=first_date,
                updated_at=last_date,
                metadata=metadata,
                source_file=source_file,
                resource_links=[],
                source_type="email",
                participants=sorted(all_participants),
                dominant_sender=dominant_sender,
                thread_id=thread_root,
                thread_type=thread_type,
                privacy_tier=3,
                person_ids=None,
            )
            notes.append(note)

    return notes


# ============================================================
# CLI Test Entry Point
# ============================================================


def main() -> None:
    """Parse an MBOX and print summary + samples."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python yahoo_mail_parser.py <path_to_mbox>")
        sys.exit(1)

    mbox_path = sys.argv[1]
    print(f"Parsing: {mbox_path}")
    print("Gap threshold: 4.0 hours\n")

    notes = parse_mbox(mbox_path)
    print(f"Parsed into {len(notes)} bursts.\n")

    # Summary
    bilateral = sum(1 for n in notes if n.thread_type == "bilateral")
    group = len(notes) - bilateral
    total_emails = sum(n.metadata.get("email_count", 0) for n in notes)

    print(f"  Source emails:  {total_emails:,}")
    print(f"  Bursts:         {len(notes):,}")
    print(f"  Bilateral:      {bilateral:,}")
    print(f"  Group:          {group:,}")

    if notes:
        dates = [n.created_at for n in notes if n.created_at]
        if dates:
            print(f"  Date range:     " f"{min(dates)[:10]} → {max(dates)[:10]}")

    # Body length stats
    lengths = [len(n.body) for n in notes]
    if lengths:
        avg_len = sum(lengths) // len(lengths)
        print(f"\n  Avg burst body: {avg_len:,} chars")
        print(f"  Max burst body: {max(lengths):,} chars")
        print(f"  Min burst body: {min(lengths):,} chars")
        empty = sum(1 for length in lengths if length == 0)
        print(f"  Empty bursts:   {empty:,}")

    # Burst size distribution
    email_counts = [n.metadata.get("email_count", 0) for n in notes]
    if email_counts:
        print("\n  Emails per burst:")
        for label, low, high in [
            ("1 email", 1, 2),
            ("2-3 emails", 2, 4),
            ("4-6 emails", 4, 7),
            ("7-10 emails", 7, 11),
            ("11+ emails", 11, 1000),
        ]:
            count = sum(1 for c in email_counts if low <= c < high)
            if count:
                print(f"    {label:<15} {count:>5}")

    # Sample bursts
    print("\n  Sample bursts:")
    samples: list[ParsedNote] = []
    for n in notes:
        ec = n.metadata.get("email_count", 0)
        if ec == 1 and len(samples) < 1:
            samples.append(n)
        elif 3 <= ec <= 5 and len(samples) < 2:
            samples.append(n)
        elif ec >= 6 and len(samples) < 3:
            samples.append(n)
        if len(samples) >= 3:
            break

    for note in samples:
        ec = note.metadata.get("email_count", 0)
        print(f"\n    Subject:  {note.title[:60]}")
        print(f"    Date:     " f"{note.created_at[:10] if note.created_at else '?'}")
        print(f"    Emails:   {ec}")
        print(f"    Type:     {note.thread_type}")
        print(f"    Participants: " f"{', '.join(note.participants or [])}")
        print(f"    Body ({len(note.body):,} chars):")
        preview = note.body[:400].replace("\n", "\n      ")
        print(f"      {preview}")
        if len(note.body) > 400:
            print("      ...")


if __name__ == "__main__":
    main()
