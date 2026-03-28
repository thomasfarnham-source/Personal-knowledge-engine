"""
Yahoo Index Query — Find Real Correspondents
===============================================
Queries the header index to identify actual human correspondents,
filtering out commercial senders, newsletters, and automated messages.

Usage:
  python yahoo_index_query.py
  python yahoo_index_query.py --search "mangan"
  python yahoo_index_query.py --contact pjmangan@gmail.com

Requires yahoo_index.db from the header scanner.
"""

import sqlite3
import os
import sys
import argparse
from typing import Any

DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"),
    "Documents",
    "dev",
    "pke-data",
    "yahoo-mail",
    "yahoo_index.db",
)

# Domains that are almost certainly commercial/automated
COMMERCIAL_DOMAINS = {
    "groupon.com",
    "ebay.com",
    "anntaylor.com",
    "harvard.edu",
    "unroll.me",
    "glassdoor.com",
    "thegreatcourses.com",
    "costco.com",
    "bananarepublic.com",
    "theatermania.com",
    "gap.com",
    "divenewsletter.com",
    "thedailygrind.news",
    "macys.com",
    "brooksbrothers.com",
    "linkedin.com",
    "dailyvoice.com",
    "facebook.com",
    "facebookmail.com",
    "twitter.com",
    "instagram.com",
    "pinterest.com",
    "youtube.com",
    "google.com",
    "apple.com",
    "amazon.com",
    "paypal.com",
    "chase.com",
    "citi.com",
    "citibank.com",
    "bankofamerica.com",
    "capitalone.com",
    "americanexpress.com",
    "nytimes.com",
    "wsj.com",
    "washingtonpost.com",
    "cnn.com",
    "substack.com",
    "mailchimp.com",
    "constantcontact.com",
    "sendgrid.net",
    "mailgun.org",
    "sparkpostmail.com",
    "e.anntaylor.com",
    "email.bananarepublic.com",
    "email.gap.com",
    "emails.macys.com",
    "email.brooksbrothers.com",
    "e.thegreatcourses.com",
    "mail.health.harvard.edu",
    "r.groupon.com",
    "reply.ebay.com",
    "online.costco.com",
    "alerts.dailyvoice.com",
    "craigslist.org",
    "yelp.com",
    "nextdoor.com",
    "eventbrite.com",
    "meetup.com",
    "ticketmaster.com",
    "uber.com",
    "lyft.com",
    "doordash.com",
    "grubhub.com",
    "netflix.com",
    "hulu.com",
    "spotify.com",
    "turbotax.com",
    "intuit.com",
    "hrblock.com",
    "usps.com",
    "ups.com",
    "fedex.com",
    "verizon.com",
    "att.com",
    "t-mobile.com",
    "xfinity.com",
    "yahoo.com",  # filters out Yahoo system messages, not your own
}

# Specific addresses to exclude (noreply, system, etc.)
EXCLUDE_PREFIXES = [
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "postmaster",
    "bounce",
    "notification",
    "alert",
    "info@",
    "support@",
    "help@",
    "team@",
    "news@",
    "newsletter@",
    "marketing@",
    "promo@",
    "deals@",
    "offers@",
    "shop@",
    "store@",
    "order",
    "billing@",
    "invoice@",
    "receipt@",
    "confirm",
    "security@",
    "account@",
    "service@",
    "admin@",
    "feedback@",
    "survey@",
    "updates@",
    "digest@",
    "hello@",
    "contact@",
    "welcome@",
    "rollup@",
]


def is_commercial(addr: str | None) -> bool:
    """Check if an email address is likely commercial/automated."""
    if not addr:
        return True
    addr = addr.lower().strip()

    # Check prefix patterns
    local_part = addr.split("@")[0] if "@" in addr else ""
    for prefix in EXCLUDE_PREFIXES:
        if local_part.startswith(prefix) or addr.startswith(prefix):
            return True

    # Check domain
    if "@" in addr:
        domain = addr.split("@")[1]
        # Check exact domain and parent domain
        parts = domain.split(".")
        for i in range(len(parts) - 1):
            check_domain = ".".join(parts[i:])
            if check_domain in COMMERCIAL_DOMAINS:
                return True

    return False


def get_human_senders(conn: sqlite3.Connection, min_count: int = 2) -> list[dict[str, Any]]:
    """Find senders that appear to be real humans."""
    cursor = conn.execute(
        """
        SELECT from_addr, from_display, COUNT(*) as cnt,
               MIN(date_str) as first_date,
               MAX(date_str) as last_date
        FROM messages
        WHERE from_addr != ''
          AND folder NOT IN ('Bulk', '[Mailstrom]/Expired',
                             '[Mailstrom]/Blocked', '[Mailstrom]/Sweeper',
                             'Unroll.me', 'Unroll.me/Unsubscribed')
        GROUP BY from_addr
        HAVING cnt >= ?
        ORDER BY cnt DESC
    """,
        (min_count,),
    )

    results: list[dict[str, Any]] = []
    for addr, display, count, first, last in cursor.fetchall():
        if not is_commercial(addr):
            # Get a cleaner display name (most recent non-empty)
            name_cursor = conn.execute(
                """
                SELECT from_display FROM messages
                WHERE from_addr = ? AND from_display != ''
                ORDER BY date_str DESC LIMIT 1
            """,
                (addr,),
            )
            name_row = name_cursor.fetchone()
            display_name = name_row[0] if name_row else ""
            # Extract just the name part
            if "<" in display_name:
                display_name = display_name.split("<")[0].strip()

            results.append(
                {
                    "addr": addr,
                    "name": display_name,
                    "count": count,
                    "first": first[:10] if first else "",
                    "last": last[:10] if last else "",
                }
            )

    return results


def search_addresses(conn: sqlite3.Connection, query: str) -> list[tuple[Any, ...]]:
    """Search for addresses matching a query string."""
    query = f"%{query}%"
    cursor = conn.execute(
        """
        SELECT from_addr, from_display, COUNT(*) as cnt,
               MIN(date_str) as first_date,
               MAX(date_str) as last_date,
               folder
        FROM messages
        WHERE (from_addr LIKE ? OR from_display LIKE ?
               OR to_addrs LIKE ? OR cc_addrs LIKE ?
               OR subject LIKE ?)
        GROUP BY from_addr
        ORDER BY cnt DESC
    """,
        (query, query, query, query, query),
    )

    return cursor.fetchall()


def contact_detail(conn: sqlite3.Connection, contact_addr: str) -> dict[str, Any]:
    """Show detailed info for a specific contact."""
    # Messages FROM this contact
    cursor = conn.execute(
        """
        SELECT folder, COUNT(*) as cnt
        FROM messages
        WHERE from_addr LIKE ?
        GROUP BY folder
        ORDER BY cnt DESC
    """,
        (f"%{contact_addr}%",),
    )
    from_folders = cursor.fetchall()

    # Messages TO this contact (in your Sent or anywhere in to/cc)
    cursor = conn.execute(
        """
        SELECT folder, COUNT(*) as cnt
        FROM messages
        WHERE to_addrs LIKE ? OR cc_addrs LIKE ?
        GROUP BY folder
        ORDER BY cnt DESC
    """,
        (f"%{contact_addr}%", f"%{contact_addr}%"),
    )
    to_folders = cursor.fetchall()

    # Date range
    cursor = conn.execute(
        """
        SELECT MIN(date_str), MAX(date_str)
        FROM messages
        WHERE from_addr LIKE ? OR to_addrs LIKE ? OR cc_addrs LIKE ?
    """,
        (f"%{contact_addr}%", f"%{contact_addr}%", f"%{contact_addr}%"),
    )
    date_range = cursor.fetchone()

    # Sample subjects
    cursor = conn.execute(
        """
        SELECT date_str, subject, from_addr
        FROM messages
        WHERE from_addr LIKE ? OR to_addrs LIKE ? OR cc_addrs LIKE ?
        ORDER BY date_str DESC
        LIMIT 10
    """,
        (f"%{contact_addr}%", f"%{contact_addr}%", f"%{contact_addr}%"),
    )
    recent = cursor.fetchall()

    # Total unique messages involving this contact
    cursor = conn.execute(
        """
        SELECT COUNT(DISTINCT id)
        FROM messages
        WHERE from_addr LIKE ? OR to_addrs LIKE ? OR cc_addrs LIKE ?
    """,
        (f"%{contact_addr}%", f"%{contact_addr}%", f"%{contact_addr}%"),
    )
    total = cursor.fetchone()[0]

    return {
        "from_folders": from_folders,
        "to_folders": to_folders,
        "date_range": date_range,
        "recent": recent,
        "total": total,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the Yahoo Mail header index")
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help="Path to SQLite index database",
    )
    parser.add_argument(
        "--search",
        type=str,
        default=None,
        help="Search for addresses/subjects matching a string",
    )
    parser.add_argument(
        "--contact",
        type=str,
        default=None,
        help="Show detailed info for a specific contact email",
    )
    parser.add_argument(
        "--min",
        type=int,
        default=3,
        help="Minimum message count to include (default: 3)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"ERROR: Database not found at {args.db}")
        sys.exit(1)

    conn = sqlite3.connect(args.db)

    if args.search:
        print(f"Searching for: {args.search}\n")
        results = search_addresses(conn, args.search)
        print(f"{'Address':<45} {'Name':<25} {'Count':>6} {'Folder'}")
        print("-" * 100)
        for addr, display, count, first, last, folder in results:
            name = display.split("<")[0].strip() if display else ""
            print(f"{addr:<45} {name[:24]:<25} {count:>6}  {folder}")

    elif args.contact:
        print(f"Contact detail: {args.contact}\n")
        detail = contact_detail(conn, args.contact)

        print(f"Total messages involving this contact: {detail['total']:,}")
        if detail["date_range"][0]:
            print(f"Date range: {detail['date_range'][0][:10]} → {detail['date_range'][1][:10]}")

        print("\nMessages FROM this contact by folder:")
        for folder, count in detail["from_folders"]:
            print(f"  {folder:<30} {count:>6}")

        total_from = sum(c for _, c in detail["from_folders"])
        print(f"  {'TOTAL':<30} {total_from:>6}")

        print("\nMessages TO this contact by folder:")
        for folder, count in detail["to_folders"]:
            print(f"  {folder:<30} {count:>6}")

        total_to = sum(c for _, c in detail["to_folders"])
        print(f"  {'TOTAL':<30} {total_to:>6}")

        print("\nMost recent messages:")
        for date_str, subject, from_addr in detail["recent"]:
            date = date_str[:10] if date_str else ""
            subj = subject[:55] if subject else ""
            direction = "←" if args.contact.lower() in from_addr.lower() else "→"
            print(f"  {date}  {direction}  {subj}")

    else:
        # Default: show human correspondents
        print(f"Human correspondents (min {args.min} messages):\n")
        humans = get_human_senders(conn, min_count=args.min)
        print(f"{'#':>4}  {'Address':<45} {'Name':<25} {'Count':>6}  {'First':<12} {'Last':<12}")
        print("-" * 115)
        for i, h in enumerate(humans, 1):
            print(
                f"{i:>4}  {h['addr']:<45} {h['name'][:24]:<25} "
                f"{h['count']:>6}  {h['first']:<12} {h['last']:<12}"
            )
        print(f"\nTotal human correspondents found: {len(humans)}")

    conn.close()


if __name__ == "__main__":
    main()
