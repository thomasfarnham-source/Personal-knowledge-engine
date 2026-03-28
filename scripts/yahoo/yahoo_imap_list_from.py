"""
Yahoo IMAP — List emails from a contact
=========================================
Fetches all emails FROM a contact in a given folder on the export
server and displays subject, date, and recipient list.

Usage:
  python yahoo_imap_list_from.py
"""

import imaplib
import email
import os
from email.header import decode_header
from email.utils import getaddresses
from dotenv import load_dotenv

load_dotenv()

YAHOO_EMAIL = os.getenv("YAHOO_EMAIL") or ""
YAHOO_APP_PASSWORD = os.getenv("YAHOO_APP_PASSWORD") or ""
IMAP_SERVER = "export.imap.mail.yahoo.com"
IMAP_PORT = 993

CONTACT = "pjmangan@gmail.com"
FOLDER = "Inbox"


def decode_header_value(raw: str | bytes | None) -> str:
    """Decode an email header value to a readable string."""
    if not raw:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    parts = decode_header(raw)
    decoded = ""
    for part, encoding in parts:
        if isinstance(part, bytes):
            decoded += part.decode(encoding or "utf-8", errors="replace")
        else:
            decoded += part
    return decoded


def main() -> None:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(YAHOO_EMAIL, YAHOO_APP_PASSWORD)
    print(f"Authenticated as {YAHOO_EMAIL}")
    print(f"Searching [{FOLDER}] for FROM {CONTACT}...\n")

    mail.select(f'"{FOLDER}"', readonly=True)
    status, msg_ids = mail.search(None, f'FROM "{CONTACT}"')

    if not msg_ids[0]:
        print("No messages found.")
        mail.logout()
        return

    ids = msg_ids[0].split()
    print(f"Found {len(ids)} messages. Fetching headers...\n")
    print(f"{'#':>4}  {'Date':<28} {'To/CC':<50} Subject")
    print(f"{'-' * 130}")

    for i, mid in enumerate(ids, 1):
        status, data = mail.fetch(mid, "(BODY[HEADER.FIELDS (FROM TO CC DATE SUBJECT)])")
        if not data or not isinstance(data[0], tuple):
            continue
        header_bytes = data[0][1]
        if not isinstance(header_bytes, (bytes, bytearray)):
            continue
        raw_header = header_bytes.decode("utf-8", errors="replace")
        msg = email.message_from_string(raw_header)

        date_str = msg.get("Date", "")[:27]
        subject = decode_header_value(msg.get("Subject", "(no subject)"))

        # Collect all recipients
        to_addrs = getaddresses(msg.get_all("To", []))
        cc_addrs = getaddresses(msg.get_all("CC", []))
        all_recip = to_addrs + cc_addrs

        # Format as short list of names or addresses
        recip_names = []
        for name, addr in all_recip:
            if name:
                # Use first name only to keep it compact
                recip_names.append(name.split()[0] if " " in name else name)
            else:
                recip_names.append(addr.split("@")[0])
        recip_str = ", ".join(recip_names)
        if len(recip_str) > 48:
            recip_str = recip_str[:45] + "..."

        # Truncate subject
        if len(subject) > 60:
            subject = subject[:57] + "..."

        print(f"{i:>4}  {date_str:<28} {recip_str:<50} {subject}")

    mail.logout()
    print("\nDisconnected.")


if __name__ == "__main__":
    main()
