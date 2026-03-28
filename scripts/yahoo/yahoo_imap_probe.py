"""
Yahoo Mail IMAP Probe Script
=============================
Quick diagnostic to answer three questions before building the parser:
  1. What folders exist? (especially: is Sent mail accessible?)
  2. For a test contact, how many messages are in Inbox vs Sent?
  3. What does a raw email look like? (preview one message)

Usage:
  python yahoo_imap_probe.py                          # list folders only
  python yahoo_imap_probe.py --contact someone@email.com  # count + preview for a contact

Requires YAHOO_EMAIL and YAHOO_APP_PASSWORD in .env
"""

import imaplib
import email
import os
import sys
import argparse
from typing import Any
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv()

YAHOO_EMAIL = os.getenv("YAHOO_EMAIL") or ""
YAHOO_APP_PASSWORD = os.getenv("YAHOO_APP_PASSWORD") or ""
IMAP_SERVER = "imap.mail.yahoo.com"
IMAP_PORT = 993


def connect() -> Any:
    """Connect and authenticate to Yahoo IMAP."""
    print(f"Connecting to {IMAP_SERVER}:{IMAP_PORT}...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(YAHOO_EMAIL, YAHOO_APP_PASSWORD)
    print(f"Authenticated as {YAHOO_EMAIL}\n")
    return mail


def list_folders(mail: Any) -> list[str]:
    """List all available IMAP folders."""
    print("=" * 60)
    print("AVAILABLE FOLDERS")
    print("=" * 60)
    status, folders = mail.list()
    folder_names = []
    for folder in folders:
        # Decode folder listing — format: (flags) "delimiter" "name"
        if isinstance(folder, (bytes, bytearray)):
            decoded = folder.decode("utf-8")
        elif isinstance(folder, tuple) and folder and isinstance(folder[0], (bytes, bytearray)):
            decoded = folder[0].decode("utf-8")
        else:
            decoded = str(folder)
        # Extract folder name (last quoted string)
        parts = decoded.rsplit('"', 2)
        if len(parts) >= 2:
            name = parts[-2]
        else:
            name = decoded
        folder_names.append(name)
        print(f"  {decoded}")
    print()
    return folder_names


def count_messages_from_contact(
    mail: Any,
    folder: str,
    contact_email: str,
) -> dict[str, Any] | None:
    """Count messages from/to a contact in a given folder."""
    try:
        status, _ = mail.select(f'"{folder}"', readonly=True)
        if status != "OK":
            return None

        # Search for messages from this contact
        status, from_ids = mail.search(None, f'FROM "{contact_email}"')
        from_count = len(from_ids[0].split()) if from_ids[0] else 0

        # Search for messages to this contact
        status, to_ids = mail.search(None, f'TO "{contact_email}"')
        to_count = len(to_ids[0].split()) if to_ids[0] else 0

        return {"from": from_count, "to": to_count}
    except Exception as e:
        return {"error": str(e)}


def preview_message(
    mail: Any,
    folder: str,
    contact_email: str,
) -> None:
    """Fetch and display the most recent message from a contact."""
    try:
        status, _ = mail.select(f'"{folder}"', readonly=True)
        if status != "OK":
            return

        status, msg_ids = mail.search(None, f'FROM "{contact_email}"')
        if not msg_ids[0]:
            print(f"  No messages from {contact_email} in {folder}")
            return

        # Get the most recent message
        latest_id = msg_ids[0].split()[-1]
        status, msg_data = mail.fetch(latest_id, "(RFC822)")
        if not msg_data or not isinstance(msg_data[0], tuple):
            return
        raw_email = msg_data[0][1]
        if not isinstance(raw_email, (bytes, bytearray)):
            return
        msg = email.message_from_bytes(raw_email)

        # Decode subject
        subject_raw = msg.get("Subject", "(no subject)")
        subject_parts = decode_header(subject_raw)
        subject = ""
        for part, encoding in subject_parts:
            if isinstance(part, bytes):
                subject += part.decode(encoding or "utf-8", errors="replace")
            else:
                subject += part

        print(f"  From:    {msg.get('From', '?')}")
        print(f"  To:      {msg.get('To', '?')}")
        print(f"  Date:    {msg.get('Date', '?')}")
        print(f"  Subject: {subject}")
        print(f"  Msg-ID:  {msg.get('Message-ID', '?')}")
        print(f"  In-Reply-To: {msg.get('In-Reply-To', '(none)')}")
        print(f"  References:  {msg.get('References', '(none)')}")

        # Get body preview
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, (bytes, bytearray)):
                        body = payload.decode("utf-8", errors="replace")
                    break
                elif content_type == "text/html" and not body:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, (bytes, bytearray)):
                        body = f"[HTML body, {len(payload)} bytes]"
        else:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, (bytes, bytearray)):
                body = payload.decode("utf-8", errors="replace")

        # Truncate for preview
        preview = body[:500] if body else "(empty body)"
        print(f"  Body preview:\n    {preview[:500]}")

    except Exception as e:
        print(f"  Error previewing message: {e}")


def probe_contact(
    mail: Any,
    contact_email: str,
    folder_names: list[str],
) -> None:
    """Run full probe for a specific contact across key folders."""
    print("=" * 60)
    print(f"CONTACT PROBE: {contact_email}")
    print("=" * 60)

    # Scan ALL folders — emails may be filed in named folders
    total_from = 0
    total_to = 0
    for folder in folder_names:
        counts = count_messages_from_contact(mail, folder, contact_email)
        if counts and "error" not in counts:
            from_count = int(counts.get("from", 0))
            to_count = int(counts.get("to", 0))
            has_messages = from_count > 0 or to_count > 0
            if has_messages:
                print(f"\n  [{folder}]")
                print(f"    FROM {contact_email}: {from_count} messages")
                print(f"    TO   {contact_email}: {to_count} messages")
                total_from += from_count
                total_to += to_count
        elif counts and "error" in counts:
            print(f"\n  [{folder}] Error: {counts['error']}")

    print(f"\n{'─' * 60}")
    print("  TOTALS across all folders:")
    print(f"    FROM {contact_email}: {total_from} messages")
    print(f"    TO   {contact_email}: {total_to} messages")
    print(f"    COMBINED: {total_from + total_to}")

    # Preview most recent message from Inbox
    print(f"\n{'─' * 60}")
    print(f"MOST RECENT MESSAGE (from {contact_email} in Inbox):")
    print(f"{'─' * 60}")
    mail.select("Inbox", readonly=True)
    preview_message(mail, "Inbox", contact_email)


def main() -> None:
    parser = argparse.ArgumentParser(description="Yahoo Mail IMAP probe for PKE")
    parser.add_argument(
        "--contact",
        type=str,
        help="Email address of a contact to probe",
    )
    args = parser.parse_args()

    if not YAHOO_EMAIL or not YAHOO_APP_PASSWORD:
        print("ERROR: Set YAHOO_EMAIL and YAHOO_APP_PASSWORD in .env")
        sys.exit(1)

    mail = None
    try:
        mail = connect()
        folder_names = list_folders(mail)

        if args.contact:
            probe_contact(mail, args.contact, folder_names)
        else:
            print("Run with --contact someone@email.com to probe a specific contact.")

    except imaplib.IMAP4.error as e:
        print(f"IMAP error: {e}")
        print("Check your YAHOO_EMAIL and YAHOO_APP_PASSWORD in .env")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        if mail:
            try:
                mail.logout()
                print("\nDisconnected.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
