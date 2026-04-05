"""
Yahoo Mail Selective Downloader (Pass 2)
==========================================
Fetches full email bodies for messages involving a specific contact,
using UIDs from the header index (Pass 1). Saves to a per-contact
MBOX file.

This is the second pass of the two-pass extraction strategy:
  Pass 1 (yahoo_header_scanner.py): Index headers → SQLite
  Pass 2 (this script): Fetch full bodies for target contact → MBOX

Usage:
  python yahoo_selective_download.py --contact pjmangan@gmail.com
  python yahoo_selective_download.py --contact pjmangan@gmail.com --dry-run
  python yahoo_selective_download.py --contact pjmangan@gmail.com,pj.mangan@yahoo.com

  Multiple addresses for the same person are comma-separated (no spaces).
  All addresses are treated as the same contact.

Requires:
  - YAHOO_EMAIL and YAHOO_APP_PASSWORD in .env
  - yahoo_index.db from Pass 1 (yahoo_header_scanner.py)
"""

import imaplib
import mailbox
import os
import re
import sqlite3
import sys
import time
import argparse
from dotenv import load_dotenv

load_dotenv()

YAHOO_EMAIL: str = os.getenv("YAHOO_EMAIL", "")
YAHOO_APP_PASSWORD: str = os.getenv("YAHOO_APP_PASSWORD", "")
IMAP_SERVER: str = "export.imap.mail.yahoo.com"
IMAP_PORT: int = 993

DEFAULT_DB_PATH: str = os.path.join(
    os.path.expanduser("~"),
    "Documents",
    "dev",
    "pke-data",
    "yahoo-mail",
    "yahoo_index.db",
)

DEFAULT_OUTPUT_DIR: str = os.path.join(
    os.path.expanduser("~"),
    "Documents",
    "dev",
    "pke-data",
    "yahoo-mail",
)

BATCH_SIZE: int = 10  # UIDs per FETCH — full bodies are large


def sanitize_filename(name: str) -> str:
    """Convert a contact address into a safe filename."""
    # Use first address, strip domain for readability
    local = name.split("@")[0] if "@" in name else name
    # Replace any non-alphanumeric chars
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", local)
    return safe


def find_contact_messages(
    conn: sqlite3.Connection, addresses: list[str]
) -> dict[str, list[tuple[int, str]]]:
    """
    Query the header index for all messages involving any of the
    contact's addresses. Returns dict of folder → list of (uid, direction).

    A message matches if the contact appears in FROM, TO, or CC.
    Direction is 'received' if contact is in FROM, 'sent' otherwise.
    """
    folders: dict[str, list[tuple[int, str]]] = {}

    for addr in addresses:
        addr_pattern = f"%{addr}%"

        # Messages FROM this contact (received by us)
        cursor = conn.execute(
            """SELECT uid, folder FROM messages
               WHERE from_addr LIKE ?""",
            (addr_pattern,),
        )
        for uid, folder in cursor.fetchall():
            if folder not in folders:
                folders[folder] = []
            folders[folder].append((uid, "received"))

        # Messages TO or CC this contact (sent by us)
        cursor = conn.execute(
            """SELECT uid, folder FROM messages
               WHERE (to_addrs LIKE ? OR cc_addrs LIKE ?)
               AND from_addr NOT LIKE ?""",
            (addr_pattern, addr_pattern, addr_pattern),
        )
        for uid, folder in cursor.fetchall():
            if folder not in folders:
                folders[folder] = []
            folders[folder].append((uid, "sent"))

    # Deduplicate within each folder (same UID might match FROM and TO)
    for folder in folders:
        seen: dict[int, str] = {}
        for uid, direction in folders[folder]:
            if uid not in seen:
                seen[uid] = direction
            elif direction == "received":
                # Prefer 'received' if contact is in both FROM and TO
                seen[uid] = "received"
        folders[folder] = [(uid, d) for uid, d in seen.items()]

    return folders


def download_messages(
    mail: imaplib.IMAP4_SSL,
    folder: str,
    uids: list[int],
    mbox_path: str,
    conn: sqlite3.Connection,
    progress_interval: int = 50,
) -> int:
    """
    Fetch full RFC822 messages by UID from a folder and append to MBOX.
    Marks messages as downloaded in the index. Returns count downloaded.
    """
    try:
        status, _ = mail.select(f'"{folder}"', readonly=True)
        if status != "OK":
            print(f"    Could not select folder: {folder}")
            return 0
    except Exception as e:
        print(f"    Error selecting folder {folder}: {e}")
        return 0

    mbox = mailbox.mbox(mbox_path)
    mbox.lock()

    downloaded = 0
    total = len(uids)
    start_time = time.time()

    try:
        for batch_start in range(0, total, BATCH_SIZE):
            batch = uids[batch_start : batch_start + BATCH_SIZE]
            uid_str = ",".join(str(u) for u in batch)

            try:
                status, response = mail.uid("FETCH", uid_str, "(RFC822)")
            except Exception as e:
                print(f"    Error fetching batch at {batch_start}: {e}")
                continue

            if status != "OK":
                continue

            # Parse response — pairs of (envelope, body_bytes)
            i = 0
            while i < len(response):
                item = response[i]
                if isinstance(item, tuple) and len(item) == 2:
                    raw_email = item[1]
                    if raw_email:
                        # Create mbox message from raw bytes
                        msg = mailbox.mboxMessage(raw_email)
                        mbox.add(msg)
                        downloaded += 1
                i += 1

            # Progress update
            processed = min(batch_start + BATCH_SIZE, total)
            if processed % progress_interval < BATCH_SIZE or processed == total:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = (total - processed) / rate if rate > 0 else 0
                print(
                    f"    {processed:,} / {total:,} fetched "
                    f"({processed * 100 // total}%) — "
                    f"{rate:.1f} msg/sec — "
                    f"~{remaining / 60:.1f} min remaining"
                )

    finally:
        mbox.unlock()
        mbox.close()

    # Mark as downloaded in the index
    for uid in uids:
        conn.execute(
            "UPDATE messages SET downloaded = 1 WHERE folder = ? AND uid = ?",
            (folder, uid),
        )
    conn.commit()

    return downloaded


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download emails for a specific contact from Yahoo Mail"
    )
    parser.add_argument(
        "--contact",
        type=str,
        required=True,
        help="Email address(es) of the contact, comma-separated for "
        "multiple addresses (e.g. addr1@gmail.com,addr2@yahoo.com)",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite index database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for MBOX files (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without fetching",
    )
    parser.add_argument(
        "--skip-downloaded",
        action="store_true",
        help="Skip messages already marked as downloaded in the index",
    )
    args = parser.parse_args()

    if not YAHOO_EMAIL or not YAHOO_APP_PASSWORD:
        print("ERROR: Set YAHOO_EMAIL and YAHOO_APP_PASSWORD in .env")
        sys.exit(1)

    if not os.path.exists(args.db):
        print(f"ERROR: Index database not found at {args.db}")
        print("Run yahoo_header_scanner.py first to build the index.")
        sys.exit(1)

    # Parse contact addresses
    addresses = [a.strip().lower() for a in args.contact.split(",")]
    contact_label = sanitize_filename(addresses[0])
    print(f"Contact: {', '.join(addresses)}")
    print(f"Label: {contact_label}")

    # Connect to index
    conn = sqlite3.connect(args.db)

    # Find all messages involving this contact
    folder_messages = find_contact_messages(conn, addresses)

    if not folder_messages:
        print("No messages found for this contact in the index.")
        conn.close()
        return

    # Summary
    total_messages = sum(len(msgs) for msgs in folder_messages.values())
    total_received = sum(1 for msgs in folder_messages.values() for _, d in msgs if d == "received")
    total_sent = sum(1 for msgs in folder_messages.values() for _, d in msgs if d == "sent")

    print("\nMessages found in index:")
    print(f"  Total:    {total_messages:,}")
    print(f"  Received: {total_received:,} (from contact)")
    print(f"  Sent:     {total_sent:,} (to contact)")
    print("\n  By folder:")
    for folder, msgs in sorted(folder_messages.items(), key=lambda x: -len(x[1])):
        received = sum(1 for _, d in msgs if d == "received")
        sent = sum(1 for _, d in msgs if d == "sent")
        print(f"    {folder:<30} {len(msgs):>6}  (←{received} →{sent})")

    if args.dry_run:
        print("\nDry run — no messages downloaded.")
        conn.close()
        return

    # Prepare output
    os.makedirs(args.output_dir, exist_ok=True)
    mbox_path = os.path.join(args.output_dir, f"{contact_label}.mbox")
    print(f"\nOutput: {mbox_path}")

    if os.path.exists(mbox_path) and not args.skip_downloaded:
        print(f"WARNING: {mbox_path} already exists.")
        response = input("Overwrite? (y/n): ").strip().lower()
        if response != "y":
            print("Aborted.")
            conn.close()
            return
        os.remove(mbox_path)

    # Connect to IMAP
    print(f"\nConnecting to {IMAP_SERVER}...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(YAHOO_EMAIL, YAHOO_APP_PASSWORD)
    print(f"Authenticated as {YAHOO_EMAIL}\n")

    # Download from each folder
    grand_total = 0
    download_start = time.time()

    for folder, msgs in sorted(folder_messages.items(), key=lambda x: -len(x[1])):
        uids = [uid for uid, _ in msgs]

        # Filter already-downloaded if requested
        if args.skip_downloaded:
            placeholders = ",".join("?" * len(uids))
            query_params: list[str | int] = [folder, *uids]
            cursor = conn.execute(
                f"""SELECT uid FROM messages
                    WHERE folder = ? AND uid IN ({placeholders})
                    AND downloaded = 1""",
                query_params,
            )
            already = {row[0] for row in cursor.fetchall()}
            uids = [u for u in uids if u not in already]
            if not uids:
                print(f"  [{folder}] All {len(msgs)} messages already downloaded — skipping")
                continue

        print(f"  [{folder}] Downloading {len(uids):,} messages...")
        count = download_messages(mail, folder, uids, mbox_path, conn)
        grand_total += count

    total_time = time.time() - download_start

    # Final summary
    file_size = os.path.getsize(mbox_path) if os.path.exists(mbox_path) else 0
    size_mb = file_size / (1024 * 1024)

    print("\nDownload complete:")
    print(f"  Messages: {grand_total:,}")
    print(f"  File:     {mbox_path}")
    print(f"  Size:     {size_mb:.1f} MB")
    print(f"  Time:     {total_time / 60:.1f} minutes")

    # Cleanup
    try:
        mail.logout()
    except Exception:
        pass
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
