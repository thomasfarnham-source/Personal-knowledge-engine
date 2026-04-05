"""
Yahoo Mail Thread Analyzer
=============================
Examines thread structure in an MBOX file to inform parser design.

Analyzes:
  - Thread sizes (how many emails per thread)
  - Time gaps between replies
  - Quote patterns (how quoted text appears)
  - Content after quote stripping (how much is new vs repeated)
  - Forwarded content patterns

Usage:
  python yahoo_thread_analysis.py
  python yahoo_thread_analysis.py --mbox /path/to/file.mbox
"""

import mailbox
import os
import re
import sys
from collections import Counter, defaultdict
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any

DEFAULT_MBOX_PATH: str = os.path.join(
    os.path.expanduser("~"),
    "Documents",
    "dev",
    "pke-data",
    "yahoo-mail",
    "pjmangan.mbox",
)


def decode_header_value(raw: str | None) -> str:
    """Decode RFC2047 header."""
    if not raw:
        return ""
    try:
        parts = decode_header(raw)
        decoded = ""
        for part, enc in parts:
            if isinstance(part, bytes):
                decoded += part.decode(enc or "utf-8", errors="replace")
            else:
                decoded += part
        return decoded
    except Exception:
        return str(raw)


def parse_date_dt(msg: mailbox.mboxMessage) -> datetime | None:
    """Parse date header to datetime object."""
    date_str = msg.get("Date", "")
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def extract_plain_body(msg: mailbox.mboxMessage) -> str:
    """Extract plain text body from a message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                if part.get_content_disposition() == "attachment":
                    continue
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")
                    except Exception:
                        return payload.decode("utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            charset = msg.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except Exception:
                return payload.decode("utf-8", errors="replace")
    return ""


def get_thread_root(msg: mailbox.mboxMessage) -> str:
    """
    Get the thread root Message-ID from References header.
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

    # No references — this message IS the thread root
    return msg.get("Message-ID", f"<unknown-{id(msg)}>")


# --- Quote detection patterns ---

# "On [date], [person] wrote:" pattern
ATTRIBUTION_PATTERN: re.Pattern[str] = re.compile(r"^On .{10,80} wrote:\s*$", re.MULTILINE)

# "> " quoted line
QUOTE_LINE_PATTERN: re.Pattern[str] = re.compile(r"^>+\s?", re.MULTILINE)

# Forwarded message delimiter
FORWARD_PATTERN: re.Pattern[str] = re.compile(r"-{5,}\s*Forwarded message\s*-{5,}", re.IGNORECASE)

# "From: ... Sent: ... To: ... Subject: ..." Outlook-style quote header
OUTLOOK_QUOTE_PATTERN: re.Pattern[str] = re.compile(
    r"^From:.*\nSent:.*\nTo:.*\nSubject:.*$", re.MULTILINE
)

# "Sent from my iPhone" and similar
SENT_FROM_PATTERN: re.Pattern[str] = re.compile(
    r"^Sent from my (?:iPhone|iPad|Tricorder|BlackBerry).*$", re.MULTILINE
)


def analyze_quote_patterns(body: str) -> dict[str, Any]:
    """Analyze what kinds of quoting appear in a message body."""
    result: dict[str, Any] = {
        "has_angle_quotes": False,
        "has_attribution_line": False,
        "has_forward": False,
        "has_outlook_quote": False,
        "has_sent_from": False,
        "total_lines": 0,
        "quoted_lines": 0,
        "new_lines": 0,
        "new_chars": 0,
        "total_chars": len(body),
    }

    lines = body.split("\n")
    result["total_lines"] = len(lines)

    # Count quoted vs new lines
    in_quote_block = False
    new_content_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Check for attribution line ("On ... wrote:")
        if ATTRIBUTION_PATTERN.match(line):
            result["has_attribution_line"] = True
            in_quote_block = True
            continue

        # Check for angle-bracket quotes
        if stripped.startswith(">"):
            result["has_angle_quotes"] = True
            result["quoted_lines"] += 1
            continue

        # Check for forward delimiter
        if FORWARD_PATTERN.search(line):
            result["has_forward"] = True
            break  # Everything after is forwarded

        # Check for Outlook-style quote
        if OUTLOOK_QUOTE_PATTERN.match(line):
            result["has_outlook_quote"] = True
            in_quote_block = True
            continue

        # Check for "Sent from" signatures
        if SENT_FROM_PATTERN.match(line):
            result["has_sent_from"] = True
            continue

        if not in_quote_block:
            new_content_lines.append(line)

    result["new_lines"] = len(new_content_lines)
    result["new_chars"] = sum(len(line) for line in new_content_lines)

    return result


def strip_quoted_content(body: str) -> str:
    """
    Strip quoted content from an email body, returning only new content.
    This is a best-effort extraction — not perfect, but good enough
    to measure how much content is new vs repeated.
    """
    lines = body.split("\n")
    new_lines: list[str] = []
    stop = False

    for line in lines:
        stripped = line.strip()

        # Stop at forwarded content
        if FORWARD_PATTERN.search(line):
            break

        # Skip attribution lines
        if ATTRIBUTION_PATTERN.match(line):
            stop = True
            continue

        # Skip angle-bracket quotes
        if stripped.startswith(">"):
            continue

        # Skip "Sent from" signatures
        if SENT_FROM_PATTERN.match(line):
            continue

        # If we hit an attribution line, skip everything after
        if stop:
            # But if we see a non-empty, non-quoted line after
            # the attribution, we might be in a new section
            # (e.g. someone wrote above and below a quote)
            if stripped and not stripped.startswith(">"):
                # This could be content after a quote block
                # Be conservative — stop collecting
                pass
            continue

        new_lines.append(line)

    result = "\n".join(new_lines).strip()
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Analyze email thread structure in an MBOX file")
    parser.add_argument(
        "--mbox",
        default=DEFAULT_MBOX_PATH,
        help=f"Path to MBOX file (default: {DEFAULT_MBOX_PATH})",
    )
    args = parser.parse_args()

    if not os.path.exists(args.mbox):
        print(f"ERROR: MBOX not found at {args.mbox}")
        sys.exit(1)

    mbox = mailbox.mbox(args.mbox)
    total = len(mbox)
    print(f"MBOX: {args.mbox}")
    print(f"Total messages: {total}\n")

    # --- Build thread map ---
    threads: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for msg in mbox:
        thread_root = get_thread_root(msg)
        date_dt = parse_date_dt(msg)
        body = extract_plain_body(msg)
        subject = decode_header_value(msg.get("Subject", ""))
        from_addr = msg.get("From", "")
        message_id = msg.get("Message-ID", "")

        threads[thread_root].append(
            {
                "message_id": message_id,
                "date": date_dt,
                "subject": subject,
                "from": from_addr,
                "body": body,
                "body_len": len(body),
            }
        )

    # Sort each thread by date
    for thread_id in threads:
        threads[thread_id].sort(
            key=lambda m: m["date"] or datetime.min.replace(tzinfo=timezone.utc)
        )

    # --- Thread size analysis ---
    thread_sizes = [len(msgs) for msgs in threads.values()]
    size_counter = Counter(thread_sizes)

    print("=" * 60)
    print("THREAD SIZE DISTRIBUTION")
    print("=" * 60)
    print(f"  Total threads:     {len(threads):,}")
    print(f"  Standalone (1):    {size_counter.get(1, 0):,}")
    print(f"  2 messages:        {size_counter.get(2, 0):,}")
    print(f"  3-5 messages:      {sum(size_counter[k] for k in range(3, 6)):,}")
    print(f"  6-10 messages:     {sum(size_counter[k] for k in range(6, 11)):,}")
    print(f"  11-20 messages:    {sum(size_counter[k] for k in range(11, 21)):,}")
    print(f"  20+ messages:      {sum(size_counter[k] for k in size_counter if k > 20):,}")

    # Show the largest threads
    large_threads = sorted(threads.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    print("\n  Top 10 largest threads:")
    for thread_id, msgs in large_threads:
        subject = msgs[0]["subject"][:50] if msgs[0]["subject"] else "(no subject)"
        first = msgs[0]["date"].strftime("%Y-%m-%d") if msgs[0]["date"] else "?"
        last = msgs[-1]["date"].strftime("%Y-%m-%d") if msgs[-1]["date"] else "?"
        print(f"    {len(msgs):>3} msgs  {first} → {last}  {subject}")

    # --- Time gap analysis ---
    print(f"\n{'=' * 60}")
    print("TIME GAPS BETWEEN REPLIES")
    print("=" * 60)

    gaps_hours: list[float] = []
    for thread_id, msgs in threads.items():
        if len(msgs) < 2:
            continue
        for i in range(1, len(msgs)):
            d1 = msgs[i - 1]["date"]
            d2 = msgs[i]["date"]
            if d1 and d2:
                gap = (d2 - d1).total_seconds() / 3600
                if gap >= 0:
                    gaps_hours.append(gap)

    if gaps_hours:
        gaps_hours.sort()
        print(f"  Total reply gaps:  {len(gaps_hours):,}")
        print(f"  Median gap:        {gaps_hours[len(gaps_hours)//2]:.1f} hours")
        print(f"  Mean gap:          {sum(gaps_hours)/len(gaps_hours):.1f} hours")
        print(f"  Min gap:           {min(gaps_hours):.2f} hours")
        print(f"  Max gap:           {max(gaps_hours):.1f} hours")

        # Distribution buckets
        buckets = [
            ("< 1 hour", 0, 1),
            ("1-4 hours", 1, 4),
            ("4-12 hours", 4, 12),
            ("12-24 hours", 12, 24),
            ("1-3 days", 24, 72),
            ("3-7 days", 72, 168),
            ("1-4 weeks", 168, 672),
            ("4+ weeks", 672, float("inf")),
        ]
        print("\n  Gap distribution:")
        for label, low, high in buckets:
            count = sum(1 for g in gaps_hours if low <= g < high)
            pct = count * 100 // len(gaps_hours) if gaps_hours else 0
            bar = "█" * (pct // 2)
            print(f"    {label:<15} {count:>5}  ({pct:>2}%) {bar}")

    # --- Quote pattern analysis ---
    print(f"\n{'=' * 60}")
    print("QUOTE PATTERNS")
    print("=" * 60)

    pattern_counts: dict[str, int] = {
        "angle_quotes": 0,
        "attribution_line": 0,
        "forward": 0,
        "outlook_quote": 0,
        "sent_from": 0,
    }

    total_chars = 0
    new_chars_total = 0
    bodies_analyzed = 0

    for msgs in threads.values():
        for msg_data in msgs:
            body = msg_data["body"]
            if not body:
                continue

            analysis = analyze_quote_patterns(body)
            bodies_analyzed += 1
            total_chars += analysis["total_chars"]
            new_chars_total += analysis["new_chars"]

            if analysis["has_angle_quotes"]:
                pattern_counts["angle_quotes"] += 1
            if analysis["has_attribution_line"]:
                pattern_counts["attribution_line"] += 1
            if analysis["has_forward"]:
                pattern_counts["forward"] += 1
            if analysis["has_outlook_quote"]:
                pattern_counts["outlook_quote"] += 1
            if analysis["has_sent_from"]:
                pattern_counts["sent_from"] += 1

    print(f"  Messages analyzed: {bodies_analyzed:,}")
    print("\n  Pattern frequency:")
    for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        pct = count * 100 // bodies_analyzed if bodies_analyzed else 0
        print(f"    {pattern:<25} {count:>5}  ({pct}%)")

    if total_chars > 0:
        ratio = new_chars_total * 100 // total_chars
        print("\n  Content ratio:")
        print(f"    Total chars:    {total_chars:,}")
        print(f"    New chars:      {new_chars_total:,}")
        print(f"    New content:    {ratio}%")
        print(f"    Redundant:      {100 - ratio}%")

    # --- Content after stripping ---
    print(f"\n{'=' * 60}")
    print("CONTENT AFTER QUOTE STRIPPING")
    print("=" * 60)

    stripped_lengths: list[int] = []
    empty_after_strip = 0

    for msgs in threads.values():
        for msg_data in msgs:
            body = msg_data["body"]
            if not body:
                continue
            stripped = strip_quoted_content(body)
            stripped_lengths.append(len(stripped))
            if not stripped.strip():
                empty_after_strip += 1

    if stripped_lengths:
        avg = sum(stripped_lengths) // len(stripped_lengths)
        non_empty = [length for length in stripped_lengths if length > 0]
        avg_non_empty = sum(non_empty) // len(non_empty) if non_empty else 0

        print(
            f"  Messages with content after stripping: "
            f"{len(stripped_lengths) - empty_after_strip:,}"
        )
        print(f"  Messages empty after stripping:        " f"{empty_after_strip:,}")
        print(f"  Avg stripped body length (all):         {avg:,} chars")
        print(f"  Avg stripped body length (non-empty):   {avg_non_empty:,} chars")

        # Length distribution
        len_buckets = [
            ("< 50 chars", 0, 50),
            ("50-200 chars", 50, 200),
            ("200-500 chars", 200, 500),
            ("500-1000 chars", 500, 1000),
            ("1K-5K chars", 1000, 5000),
            ("5K+ chars", 5000, float("inf")),
        ]
        print("\n  Stripped body length distribution:")
        for label, low, high in len_buckets:
            count = sum(1 for length in stripped_lengths if low <= length < high)
            print(f"    {label:<20} {count:>5}")

    # --- Sample threads ---
    print(f"\n{'=' * 60}")
    print("SAMPLE THREADS (showing quote stripping)")
    print("=" * 60)

    # Pick a few multi-message threads
    sample_threads = [(tid, msgs) for tid, msgs in threads.items() if 3 <= len(msgs) <= 6][:3]

    for thread_id, msgs in sample_threads:
        subject = msgs[0]["subject"][:60] if msgs[0]["subject"] else "(no subject)"
        print(f"\n  Thread: {subject}")
        print(f"  Messages: {len(msgs)}")
        print(f"  {'─' * 55}")

        for msg_data in msgs:
            date = msg_data["date"].strftime("%Y-%m-%d %H:%M") if msg_data["date"] else "?"
            sender = msg_data["from"][:30] if msg_data["from"] else "?"
            body = msg_data["body"]
            stripped = strip_quoted_content(body) if body else ""

            print(f"\n    {date}  {sender}")
            print(f"    Original: {len(body):,} chars → Stripped: {len(stripped):,} chars")
            if stripped:
                preview = stripped[:200].replace("\n", "\n      ")
                print(f"      {preview}")


if __name__ == "__main__":
    main()
