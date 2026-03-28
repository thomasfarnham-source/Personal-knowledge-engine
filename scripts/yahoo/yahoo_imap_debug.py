"""
Yahoo IMAP Debug — Targeted Search
====================================
Hunt for a specific known email using multiple search strategies
to identify why IMAP search is missing messages.

Usage:
  python yahoo_imap_debug.py
"""

import imaplib
import os
from typing import Any
from dotenv import load_dotenv

load_dotenv()

YAHOO_EMAIL = os.getenv("YAHOO_EMAIL") or ""
YAHOO_APP_PASSWORD = os.getenv("YAHOO_APP_PASSWORD") or ""
IMAP_SERVER = "imap.mail.yahoo.com"
IMAP_PORT = 993

# Known email details
CONTACT = "pjmangan@gmail.com"
SUBJECT_FRAGMENT = "Delta Chi Reunion"
DATE = "7-Sep-2021"  # IMAP date format: DD-Mon-YYYY


def try_search(
    mail: Any,
    folder: str,
    label: str,
    *search_criteria: str,
) -> int:
    """Run a search and report results."""
    try:
        mail.select(f'"{folder}"', readonly=True)
        status, msg_ids = mail.search(None, *search_criteria)
        count = len(msg_ids[0].split()) if msg_ids[0] else 0
        print(f"  {label:40s} → {count} results")
        if count > 0 and count <= 5:
            # Show brief details of matches
            for mid in msg_ids[0].split():
                status, data = mail.fetch(mid, "(BODY[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if not data or not isinstance(data[0], tuple):
                    continue
                header_bytes = data[0][1]
                if not isinstance(header_bytes, (bytes, bytearray)):
                    continue
                header = header_bytes.decode("utf-8", errors="replace")
                print(f"    {header.strip()[:120]}")
        return count
    except Exception as e:
        print(f"  {label:40s} → ERROR: {e}")
        return 0


def main() -> None:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(YAHOO_EMAIL, YAHOO_APP_PASSWORD)
    print(f"Authenticated as {YAHOO_EMAIL}\n")

    # Search Inbox specifically — Yahoo web UI says it's in Inbox
    folder = "Inbox"
    print(f"{'=' * 60}")
    print(f"SEARCHING [{folder}] for Delta Chi Reunion email")
    print(f"{'=' * 60}\n")

    # Strategy 1: FROM exact match
    try_search(mail, folder, "FROM exact", f'FROM "{CONTACT}"')

    # Strategy 2: SUBJECT match
    try_search(mail, folder, "SUBJECT match", 'SUBJECT "Delta Chi Reunion"')

    # Strategy 3: SUBJECT + date range
    try_search(
        mail,
        folder,
        "SUBJECT + date range",
        'SUBJECT "Delta Chi" SINCE "1-Sep-2021" BEFORE "15-Sep-2021"',
    )

    # Strategy 4: FROM + date range
    try_search(
        mail,
        folder,
        "FROM + date range",
        f'FROM "{CONTACT}" SINCE "1-Sep-2021" BEFORE "15-Sep-2021"',
    )

    # Strategy 5: All messages on that date
    try_search(mail, folder, "ON specific date", f'ON "{DATE}"')

    # Strategy 6: Date range only (how many total?)
    try_search(mail, folder, "Date range (all senders)", 'SINCE "1-Sep-2021" BEFORE "15-Sep-2021"')

    # Strategy 7: TEXT body search
    try_search(mail, folder, "TEXT 'Delta Chi'", 'TEXT "Delta Chi"')

    # Strategy 8: TEXT search for the other participant
    try_search(mail, folder, "TEXT 'Hornbrook'", 'TEXT "Hornbrook"')

    # Strategy 9: How many total messages in Inbox?
    mail.select("Inbox", readonly=True)
    status, msg_ids = mail.search(None, "ALL")
    total = len(msg_ids[0].split()) if msg_ids[0] else 0
    print(f"\n  {'Total messages in Inbox':40s} → {total}")

    # Strategy 10: Check if Inbox has messages from 2021 at all
    try_search(mail, folder, "Any messages from 2021", 'SINCE "1-Jan-2021" BEFORE "1-Jan-2022"')

    mail.logout()
    print("\nDisconnected.")


if __name__ == "__main__":
    main()
