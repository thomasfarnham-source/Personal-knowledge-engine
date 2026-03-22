"""
pke/cli/ingest_imessage.py

Typer CLI for iMessage ingestion.

Usage:
    # Ingest a single CSV export
    pke ingest-imessage file "path/to/Messages - Patrick Mangan.csv"

    # Ingest all CSV exports in a directory
    pke ingest-imessage dir "C:/Users/thoma/Documents/dev/pke-data/imessage-exports"

    # Dry run — parse and report without writing to DB
    pke ingest-imessage file "..." --dry-run

Note: environment variables are loaded by pke/cli/main.py via load_dotenv()
before any sub-app command runs. No need to load them here.
"""

import logging
from pathlib import Path
from typing import Any

import typer

from pke.ingestion.imessage_ingestor import IMessageIngestor, IMessageIngestionResult

logger = logging.getLogger(__name__)

imessage_app = typer.Typer(
    help="Ingest iMessage CSV exports into the PKE database."
)


def _get_db(dry_run: bool) -> Any:
    """Build and return a SupabaseClient — real or dry-run."""
    from pke.supabase_client import SupabaseClient

    if dry_run:
        typer.echo("DRY RUN — no writes will be made to the database")
        return SupabaseClient(dry_run=True)

    from supabase import create_client
    import os

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return SupabaseClient(client=create_client(url, key))


def _print_result(result: IMessageIngestionResult) -> None:
    status = "~" if result.dry_run else "✓"
    typer.echo(
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
    typer.echo(
        f"─────────────────────────────\n"
        f"  Total threads:  {len(results)}\n"
        f"  Total messages: {total_messages}\n"
        f"  Total bursts:   {total_bursts}\n"
        f"  Total chunks:   {total_chunks}\n"
    )


@imessage_app.command("file")
def ingest_file(
    path: str = typer.Argument(..., help="Path to a single iMazing CSV export file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse without writing to DB."),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug logging."),
) -> None:
    """Ingest a single iMazing CSV export file."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not Path(path).exists():
        typer.echo(f"Error: file not found: {path}", err=True)
        raise typer.Exit(1)

    if not path.endswith(".csv"):
        typer.echo(f"Error: expected a .csv file, got: {path}", err=True)
        raise typer.Exit(1)

    db = _get_db(dry_run)
    ingestor = IMessageIngestor(db)

    try:
        result = ingestor.ingest_csv(path)
        _print_result(result)
    except Exception as e:
        typer.echo(f"Ingestion failed: {e}", err=True)
        raise typer.Exit(1)


@imessage_app.command("dir")
def ingest_dir(
    path: str = typer.Argument(..., help="Path to folder containing iMazing CSV exports."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse without writing to DB."),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug logging."),
) -> None:
    """Ingest all iMazing CSV exports in a directory."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not Path(path).is_dir():
        typer.echo(f"Error: directory not found: {path}", err=True)
        raise typer.Exit(1)

    db = _get_db(dry_run)
    ingestor = IMessageIngestor(db)

    try:
        results = ingestor.ingest_directory(path)
        for result in results:
            _print_result(result)
        if results:
            _print_summary(results)
    except Exception as e:
        typer.echo(f"Ingestion failed: {e}", err=True)
        raise typer.Exit(1)
