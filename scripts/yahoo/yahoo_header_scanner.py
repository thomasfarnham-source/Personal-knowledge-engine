"""
Yahoo Mail Header Scanner (Pass 1)
====================================
Connects to Yahoo's export IMAP server and downloads message headers
for ALL messages across ALL folders. Stores them in a local SQLite
database for querying and contact analysis.

This is the first pass of a two-pass strategy:
  Pass 1 (this script): Index headers → local SQLite
  Pass 2 (separate script): Fetch full bodies for target contacts → MBOX

The export server (export.imap.mail.yahoo.com) bypasses Yahoo's 10K
message-per-folder IMAP limit. Headers are fetched by UID, not by
SEARCH, avoiding the search result cap.

Usage:
  python yahoo_header_scanner.py                    # full scan
  python yahoo_header_scanner.py --folders Inbox,Sent  # specific folders
  python yahoo_header_scanner.py --resume           # skip already-scanned folders

Requires YAHOO_EMAIL and YAHOO_APP_PASSWORD in .env
"""

import imaplib
import email
import os
import sys
import sqlite3
import argparse
import time
from typing import Any
from email.header import decode_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from dotenv import load_dotenv

load_dotenv()

YAHOO_EMAIL = os.getenv("YAHOO_EMAIL") or ""
YAHOO_APP_PASSWORD = os.getenv("YAHOO_APP_PASSWORD") or ""
IMAP_SERVER = "export.imap.mail.yahoo.com"
IMAP_PORT = 993

# Default database location
DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"),
    "Documents",
    "dev",
    "pke-data",
    "yahoo-mail",
    "yahoo_index.db",
)

BATCH_SIZE = 50  # UIDs per FETCH request — balance speed vs memory


def decode_header_value(raw: str | bytes | None) -> str:
    """Decode an RFC2047-encoded header value to a string."""
    if not raw:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
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


def extract_addresses(msg: Message, header_name: str) -> str:
    """Extract email addresses from a header field as a comma-separated string."""
    raw_values = msg.get_all(header_name, [])
    if not raw_values:
        return ""
    # Decode any RFC2047 encoding in the header values
    decoded_values = [decode_header_value(v) for v in raw_values]
    pairs = getaddresses(decoded_values)
    # Return as "name <addr>, name <addr>" or just "addr, addr"
    results = []
    for name, addr in pairs:
        if name and addr:
            results.append(f"{name} <{addr}>")
        elif addr:
            results.append(addr)
    return ", ".join(results)


def extract_email_only(msg: Message, header_name: str) -> str:
    """Extract just the email addresses (no display names) as comma-separated."""
    raw_values = msg.get_all(header_name, [])
    if not raw_values:
        return ""
    decoded_values = [decode_header_value(v) for v in raw_values]
    pairs = getaddresses(decoded_values)
    return ", ".join(addr.lower() for _, addr in pairs if addr)


def parse_date(msg: Message) -> str:
    """Extract and normalize the Date header to ISO format."""
    date_str = msg.get("Date", "")
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return date_str[:50]


def init_db(db_path: str) -> sqlite3.Connection:
    """Create the SQLite database and tables if they don't exist."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            folder TEXT NOT NULL,
            from_addr TEXT,
            from_display TEXT,
            to_addrs TEXT,
            cc_addrs TEXT,
            date_str TEXT,
            subject TEXT,
            message_id TEXT,
            in_reply_to TEXT,
            references_hdr TEXT,
            downloaded INTEGER DEFAULT 0,
            UNIQUE(folder, uid)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_log (
            folder TEXT PRIMARY KEY,
            total_messages INTEGER,
            scanned_count INTEGER,
            completed_at TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_from
        ON messages(from_addr)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_to
        ON messages(to_addrs)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_folder
        ON messages(folder)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_message_id
        ON messages(message_id)
    """)
    conn.commit()
    return conn


def get_folder_names(mail: imaplib.IMAP4_SSL) -> list[str]:
    """Extract folder names from IMAP LIST response."""
    status, folders = mail.list()
    names = []
    for folder in folders:
        if isinstance(folder, (bytes, bytearray)):
            decoded = folder.decode("utf-8")
        elif isinstance(folder, tuple) and folder and isinstance(folder[0], (bytes, bytearray)):
            decoded = folder[0].decode("utf-8")
        else:
            continue
        parts = decoded.rsplit('"', 2)
        if len(parts) >= 2:
            names.append(parts[-2])
    return names


def get_completed_folders(conn: sqlite3.Connection) -> set[str]:
    """Return set of folders that have already been fully scanned."""
    cursor = conn.execute("SELECT folder FROM scan_log WHERE completed_at IS NOT NULL")
    return {row[0] for row in cursor.fetchall()}


def scan_folder(
    mail: Any,
    conn: sqlite3.Connection,
    folder: str,
    progress_interval: int = 1000,
) -> int:
    """Scan all message headers in a folder and store in SQLite."""
    try:
        status, data = mail.select(f'"{folder}"', readonly=True)
        if status != "OK":
            print(f"  Could not select folder: {folder}")
            return 0
    except Exception as e:
        print(f"  Error selecting folder {folder}: {e}")
        return 0

    # Get total message count
    status, all_uids_raw = mail.uid("SEARCH", "ALL")
    if not all_uids_raw or not isinstance(all_uids_raw[0], (bytes, bytearray)):
        print(f"  [{folder}] Empty folder — skipping")
        return 0
    if not all_uids_raw[0]:
        print(f"  [{folder}] Empty folder — skipping")
        return 0

    all_uids = all_uids_raw[0].split()
    total = len(all_uids)
    print(f"  [{folder}] {total:,} messages to scan")

    # Check what we already have for this folder
    cursor = conn.execute("SELECT COUNT(*) FROM messages WHERE folder = ?", (folder,))
    existing = cursor.fetchone()[0]
    if existing > 0:
        print(f"    ({existing:,} already indexed — fetching remaining)")

    scanned = 0
    inserted = 0
    start_time = time.time()

    # Process in batches
    for batch_start in range(0, total, BATCH_SIZE):
        batch_uids = all_uids[batch_start : batch_start + BATCH_SIZE]
        uid_str = b",".join(batch_uids).decode("ascii", errors="ignore")

        try:
            status, response = mail.uid(
                "FETCH",
                uid_str,
                (
                    "(BODY.PEEK[HEADER.FIELDS "
                    "(FROM TO CC DATE SUBJECT MESSAGE-ID IN-REPLY-TO REFERENCES)])"
                ),
            )
        except Exception as e:
            print(f"    Error fetching batch at {batch_start}: {e}")
            # Try to reconnect and continue
            continue

        if status != "OK":
            continue

        # Parse response — response contains pairs of (envelope, header_bytes)
        rows_to_insert: list[tuple[Any, ...]] = []
        i = 0
        while i < len(response):
            item = response[i]
            if isinstance(item, tuple) and len(item) == 2:
                # Extract UID from the response envelope
                envelope_raw = item[0]
                if not isinstance(envelope_raw, (bytes, bytearray)):
                    i += 1
                    continue
                envelope = envelope_raw.decode("utf-8", errors="replace")
                uid = None
                for part in envelope.split():
                    if part.startswith("UID"):
                        # Next token is the UID value — but format varies
                        pass
                # Parse UID from envelope more reliably
                import re

                uid_match = re.search(r"UID (\d+)", envelope)
                if uid_match:
                    uid = int(uid_match.group(1))

                header_bytes = item[1]
                if isinstance(header_bytes, (bytes, bytearray)) and uid:
                    msg = email.message_from_bytes(header_bytes)

                    from_display = extract_addresses(msg, "From")
                    from_addr = extract_email_only(msg, "From")
                    to_addrs = extract_email_only(msg, "To")
                    cc_addrs = extract_email_only(msg, "Cc")
                    date_str = parse_date(msg)
                    subject = decode_header_value(msg.get("Subject", ""))
                    message_id = msg.get("Message-ID", "")
                    in_reply_to = msg.get("In-Reply-To", "")
                    references_hdr = msg.get("References", "")

                    rows_to_insert.append(
                        (
                            uid,
                            folder,
                            from_addr,
                            from_display,
                            to_addrs,
                            cc_addrs,
                            date_str,
                            subject,
                            message_id,
                            in_reply_to,
                            references_hdr,
                        )
                    )
            i += 1

        # Batch insert
        if rows_to_insert:
            conn.executemany(
                """INSERT OR IGNORE INTO messages
                   (uid, folder, from_addr, from_display, to_addrs,
                    cc_addrs, date_str, subject, message_id,
                    in_reply_to, references_hdr)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows_to_insert,
            )
            conn.commit()
            inserted += len(rows_to_insert)

        scanned += len(batch_uids)

        # Progress update
        if scanned % progress_interval < BATCH_SIZE:
            elapsed = time.time() - start_time
            rate = scanned / elapsed if elapsed > 0 else 0
            remaining = (total - scanned) / rate if rate > 0 else 0
            print(
                f"    {scanned:,} / {total:,} scanned "
                f"({scanned * 100 // total}%) — "
                f"{rate:.0f} msg/sec — "
                f"~{remaining / 60:.1f} min remaining"
            )

    elapsed = time.time() - start_time
    print(f"    Done: {inserted:,} new headers indexed in {elapsed:.1f}s")

    # Log completion
    conn.execute(
        """INSERT OR REPLACE INTO scan_log (folder, total_messages, scanned_count, completed_at)
           VALUES (?, ?, ?, datetime('now'))""",
        (folder, total, scanned),
    )
    conn.commit()

    return inserted


def print_summary(conn: sqlite3.Connection) -> None:
    """Print a summary of the index contents."""
    print(f"\n{'=' * 60}")
    print("INDEX SUMMARY")
    print(f"{'=' * 60}")

    cursor = conn.execute("SELECT COUNT(*) FROM messages")
    total = cursor.fetchone()[0]
    print(f"  Total messages indexed: {total:,}")

    cursor = conn.execute(
        "SELECT folder, COUNT(*) as cnt FROM messages GROUP BY folder ORDER BY cnt DESC"
    )
    print("\n  By folder:")
    for folder, count in cursor.fetchall():
        print(f"    {folder:<30} {count:>8,}")

    # Top senders
    cursor = conn.execute("""
        SELECT from_addr, COUNT(*) as cnt
        FROM messages
        WHERE from_addr != ''
        GROUP BY from_addr
        ORDER BY cnt DESC
        LIMIT 20
    """)
    print("\n  Top 20 senders:")
    for addr, count in cursor.fetchall():
        print(f"    {addr:<45} {count:>6,}")

    # Date range
    cursor = conn.execute("SELECT MIN(date_str), MAX(date_str) FROM messages WHERE date_str != ''")
    row = cursor.fetchone()
    if row[0]:
        print(f"\n  Date range: {row[0][:10]} → {row[1][:10]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Yahoo Mail header scanner — index all message headers"
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite index database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--folders",
        type=str,
        default=None,
        help="Comma-separated list of folders to scan (default: all)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip folders that have already been fully scanned",
    )
    args = parser.parse_args()

    if not YAHOO_EMAIL or not YAHOO_APP_PASSWORD:
        print("ERROR: Set YAHOO_EMAIL and YAHOO_APP_PASSWORD in .env")
        sys.exit(1)

    # Init database
    conn = init_db(args.db)
    print(f"Database: {args.db}")

    # Connect to IMAP
    print(f"Connecting to {IMAP_SERVER}...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(YAHOO_EMAIL, YAHOO_APP_PASSWORD)
    print(f"Authenticated as {YAHOO_EMAIL}\n")

    # Determine folders to scan
    if args.folders:
        folders = [f.strip() for f in args.folders.split(",")]
    else:
        folders = get_folder_names(mail)

    # Filter out already-completed folders if resuming
    if args.resume:
        completed = get_completed_folders(conn)
        before = len(folders)
        folders = [f for f in folders if f not in completed]
        skipped = before - len(folders)
        if skipped:
            print(f"Resuming — skipping {skipped} already-completed folders\n")

    print(f"Scanning {len(folders)} folders...\n")

    total_inserted = 0
    scan_start = time.time()

    for folder in folders:
        try:
            inserted = scan_folder(mail, conn, folder)
            total_inserted += inserted
        except Exception as e:
            print(f"  ERROR scanning {folder}: {e}")
            # Try to reconnect
            try:
                mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
                mail.login(YAHOO_EMAIL, YAHOO_APP_PASSWORD)
                print("  Reconnected to IMAP server")
            except Exception:
                print("  Could not reconnect — stopping")
                break

    total_time = time.time() - scan_start
    print(f"\nScan complete: {total_inserted:,} headers indexed in {total_time / 60:.1f} minutes")

    # Print summary
    print_summary(conn)

    # Cleanup
    try:
        mail.logout()
    except Exception:
        pass
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
