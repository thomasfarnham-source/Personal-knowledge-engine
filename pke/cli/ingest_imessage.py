"""
pke/cli/ingest_imessage.py

CLI entry point for iMessage ingestion.

Usage:
    # Ingest a single CSV export
    pke ingest-imessage --file "path/to/Messages - Patrick Mangan.csv"

    # Ingest all CSV exports in a directory
    pke ingest-imessage --dir "C:/Users/thoma/Documents/dev/pke-data/imessage-exports"

    # Dry run — parse and report without writing to DB
    pke ingest-imessage --file "..." --dry-run

    # Verbose logging
    pke ingest-imessage --file "..." --verbose
"""

import argparse
import logging
import os
import sys

from pke.ingestion.imessage_ingestor import IMessageIngestor, IMessageIngestionResult

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest iMessage CSV exports into the PKE database."
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--file",
        type=str,
        help="Path to a single iMazing CSV export file.",
    )
    source.add_argument(
        "--dir",
        type=str,
        help="Path to a directory containing iMazing CSV export files.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Parse and report without writing to the database.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug logging.",
    )

    args = parser.parse_args()

    # ── Logging ──────────────────────────────────────────────────
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    # ── Database client ──────────────────────────────────────────
    from pke.supabase_client import SupabaseClient

    if args.dry_run:
        db = SupabaseClient(dry_run=True)
        logger.info("DRY RUN — no writes will be made to the database")
    else:
        from supabase import create_client

        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        db = SupabaseClient(client=create_client(url, key))

    # ── Ingestor ─────────────────────────────────────────────────
    ingestor = IMessageIngestor(db)

    # ── Run ──────────────────────────────────────────────────────
    try:
        if args.file:
            _validate_file(args.file)
            result = ingestor.ingest_csv(args.file)
            _print_result(result)

        elif args.dir:
            _validate_dir(args.dir)
            results = ingestor.ingest_directory(args.dir)
            for result in results:
                _print_result(result)
            _print_summary(results)

    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        sys.exit(1)


def _validate_file(path: str) -> None:
    if not os.path.exists(path):
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    if not path.endswith(".csv"):
        print(f"Error: expected a .csv file, got: {path}", file=sys.stderr)
        sys.exit(1)


def _validate_dir(path: str) -> None:
    if not os.path.isdir(path):
        print(f"Error: directory not found: {path}", file=sys.stderr)
        sys.exit(1)


def _print_result(result: IMessageIngestionResult) -> None:
    status = "~" if result.dry_run else "✓"
    print(
        f"  {status} {result.thread_name}\n"
        f"    messages:     {result.messages_upserted}\n"
        f"    bursts:       {result.bursts_upserted}\n"
        f"    chunks:       {result.chunks_mirrored}\n"
        f"    participants: {result.participants_upserted}\n"
        f"    skipped:      {result.skipped_bursts} (no text content)\n"
    )


def _print_summary(results: list[IMessageIngestionResult]) -> None:
    total_messages = sum(r.messages_upserted for r in results)
    total_bursts = sum(r.bursts_upserted for r in results)
    total_chunks = sum(r.chunks_mirrored for r in results)
    print(
        f"─────────────────────────────\n"
        f"  Total threads:  {len(results)}\n"
        f"  Total messages: {total_messages}\n"
        f"  Total bursts:   {total_bursts}\n"
        f"  Total chunks:   {total_chunks}\n"
    )


if __name__ == "__main__":
    main()
