"""
Yahoo IMAP Export Server Test
==============================
Tests whether export.imap.mail.yahoo.com bypasses the 10,000 message
limit on the standard IMAP server.

Usage:
  python yahoo_imap_export_test.py
"""

import imaplib
import os
from dotenv import load_dotenv

load_dotenv()

YAHOO_EMAIL = os.getenv("YAHOO_EMAIL") or ""
YAHOO_APP_PASSWORD = os.getenv("YAHOO_APP_PASSWORD") or ""
IMAP_PORT = 993

SERVERS = [
    ("imap.mail.yahoo.com", "Standard IMAP"),
    ("export.imap.mail.yahoo.com", "Export IMAP"),
]

CONTACT = "pjmangan@gmail.com"


def probe_server(server: str, label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"SERVER: {label} ({server})")
    print(f"{'=' * 60}")

    try:
        mail = imaplib.IMAP4_SSL(server, IMAP_PORT)
        mail.login(YAHOO_EMAIL, YAHOO_APP_PASSWORD)
        print("  Connected and authenticated.\n")

        # Total messages in Inbox
        status, _ = mail.select("Inbox", readonly=True)
        status, all_ids = mail.search(None, "ALL")
        total = len(all_ids[0].split()) if all_ids[0] else 0
        print(f"  Total messages in Inbox:    {total}")

        # Messages from 2021
        status, ids_2021 = mail.search(None, 'SINCE "1-Jan-2021" BEFORE "1-Jan-2022"')
        count_2021 = len(ids_2021[0].split()) if ids_2021[0] else 0
        print(f"  Messages from 2021:         {count_2021}")

        # Delta Chi Reunion search
        status, subj_ids = mail.search(None, 'SUBJECT "Delta Chi"')
        subj_count = len(subj_ids[0].split()) if subj_ids[0] else 0
        print(f"  SUBJECT 'Delta Chi':        {subj_count}")

        # FROM contact
        status, from_ids = mail.search(None, f'FROM "{CONTACT}"')
        from_count = len(from_ids[0].split()) if from_ids[0] else 0
        print(f"  FROM {CONTACT}:  {from_count}")

        # Sent folder — TO contact
        mail.select("Sent", readonly=True)
        status, sent_ids = mail.search(None, f'TO "{CONTACT}"')
        sent_count = len(sent_ids[0].split()) if sent_ids[0] else 0
        print(f"  Sent TO {CONTACT}: {sent_count}")

        mail.logout()
        print("  Disconnected.")

    except Exception as e:
        print(f"  ERROR: {e}")


def main() -> None:
    for server, label in SERVERS:
        probe_server(server, label)


if __name__ == "__main__":
    main()
