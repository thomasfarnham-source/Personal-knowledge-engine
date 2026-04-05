"""
MBOX Inspector — examine message structure for parser design.
Shows headers, content types, and body samples from a few messages.

Usage:
  python yahoo_mbox_inspect.py
"""

import mailbox
import os
from email.header import decode_header

MBOX_PATH = os.path.join(
    os.path.expanduser("~"),
    "Documents",
    "dev",
    "pke-data",
    "yahoo-mail",
    "pjmangan.mbox",
)

SAMPLE_COUNT = 5  # Number of messages to inspect


def decode_header_value(raw: str) -> str:
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


def inspect_message(msg: mailbox.mboxMessage, index: int) -> None:
    """Print detailed structure of one message."""
    print(f"\n{'=' * 70}")
    print(f"MESSAGE {index}")
    print(f"{'=' * 70}")

    # Key headers
    print(f"  From:        {msg.get('From', '?')}")
    print(f"  To:          {msg.get('To', '?')}")
    print(f"  CC:          {msg.get('Cc', '(none)')}")
    print(f"  Date:        {msg.get('Date', '?')}")
    print(f"  Subject:     {decode_header_value(msg.get('Subject', ''))}")
    print(f"  Message-ID:  {msg.get('Message-ID', '?')}")
    print(f"  In-Reply-To: {msg.get('In-Reply-To', '(none)')}")
    print(f"  References:  {(msg.get('References', '(none)'))[:100]}")
    print(f"  Content-Type: {msg.get_content_type()}")
    print(f"  Is multipart: {msg.is_multipart()}")

    # Walk the MIME tree
    print("\n  MIME structure:")
    for i, part in enumerate(msg.walk()):
        content_type = part.get_content_type()
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        size = len(part.get_payload(decode=True) or b"")
        indent = "    "
        print(
            f"{indent}Part {i}: {content_type}"
            f"  disp={disposition}  file={filename}  size={size}"
        )

    # Extract text body
    plain_body = None
    html_body = None
    for part in msg.walk():
        ct = part.get_content_type()
        disp = part.get_content_disposition()
        if disp == "attachment":
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except Exception:
            text = payload.decode("utf-8", errors="replace")

        if ct == "text/plain" and plain_body is None:
            plain_body = text
        elif ct == "text/html" and html_body is None:
            html_body = text

    print(
        f"\n  Plain text body: {'YES' if plain_body else 'NO'}" f" ({len(plain_body)} chars)"
        if plain_body
        else ""
    )
    print(
        f"  HTML body: {'YES' if html_body else 'NO'}" f" ({len(html_body)} chars)"
        if html_body
        else ""
    )

    # Show body preview
    if plain_body:
        preview = plain_body[:500].replace("\n", "\n    ")
        print(f"\n  Plain text preview:\n    {preview}")
    elif html_body:
        preview = html_body[:500].replace("\n", "\n    ")
        print(f"\n  HTML preview (no plain text available):\n    {preview}")


def main() -> None:
    if not os.path.exists(MBOX_PATH):
        print(f"ERROR: MBOX not found at {MBOX_PATH}")
        return

    mbox = mailbox.mbox(MBOX_PATH)
    total = len(mbox)
    print(f"MBOX: {MBOX_PATH}")
    print(f"Total messages: {total}")

    # Sample: first message, last message, and a few from the middle
    indices = [0, total // 4, total // 2, 3 * total // 4, total - 1]
    indices = indices[:SAMPLE_COUNT]
    messages = list(mbox)

    for idx in indices:
        msg = messages[idx]
        inspect_message(msg, idx)

    # Summary stats
    print(f"\n{'=' * 70}")
    print("CORPUS SUMMARY")
    print(f"{'=' * 70}")

    plain_count = 0
    html_only_count = 0
    multipart_count = 0
    attachment_count = 0
    content_types: dict[str, int] = {}

    for msg in mbox:
        if msg.is_multipart():
            multipart_count += 1

        has_plain = False
        has_html = False
        for part in msg.walk():
            ct = part.get_content_type()
            content_types[ct] = content_types.get(ct, 0) + 1
            if ct == "text/plain":
                has_plain = True
            elif ct == "text/html":
                has_html = True
            if part.get_content_disposition() == "attachment":
                attachment_count += 1

        if has_plain:
            plain_count += 1
        elif has_html:
            html_only_count += 1

    print(f"  Multipart messages:  {multipart_count:,}")
    print(f"  With plain text:     {plain_count:,}")
    print(f"  HTML only (no plain):{html_only_count:,}")
    print(f"  Total attachments:   {attachment_count:,}")
    print("\n  Content types found:")
    for ct, count in sorted(content_types.items(), key=lambda x: -x[1]):
        print(f"    {ct:<40} {count:>6}")


if __name__ == "__main__":
    main()
