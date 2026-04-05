"""
CLI: pke ingest-yahoo
=======================
Ingest a Yahoo Mail MBOX file into Supabase.

Usage:
    python -m pke.cli.ingest_yahoo <mbox_path>
    python -m pke.cli.ingest_yahoo <mbox_path> --dry-run
    python -m pke.cli.ingest_yahoo <mbox_path> --no-embed
"""

import typer
from pathlib import Path

app = typer.Typer()


@app.command()
def ingest_yahoo(
    mbox_path: str = typer.Argument(..., help="Path to the MBOX file to ingest"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Parse and report without writing to Supabase"
    ),
    no_embed: bool = typer.Option(
        False, "--no-embed", help="Skip embedding generation (backfill later)"
    ),
    owner_address: str = typer.Option(
        "thomas.farnham@yahoo.com",
        "--owner",
        help="Owner email address for direction detection",
    ),
    gap_hours: float = typer.Option(
        4.0,
        "--gap-hours",
        help="Time gap (hours) to segment threads into bursts",
    ),
) -> None:
    """Ingest a Yahoo Mail MBOX file into the PKE knowledge base."""

    if not Path(mbox_path).exists():
        typer.echo(f"ERROR: File not found: {mbox_path}")
        raise typer.Exit(1)

    if dry_run:
        # Dry run — no clients needed
        from pke.ingestion.yahoo_mail_ingestor import (
            IngestionReport,
            participant_hash,
        )
        from pke.parsers.yahoo_mail_parser import (
            parse_emails,
            parse_mbox,
        )
        from typing import Any

        report = IngestionReport(mbox_path=mbox_path)
        notes = parse_mbox(mbox_path, owner_address, gap_hours)
        emails = parse_emails(mbox_path, owner_address)

        report.emails_parsed = len(emails)
        report.bursts_created = len(notes)

        conv_hashes: set[str] = set()
        for note in notes:
            if note.participants:
                conv_hashes.add(participant_hash(note.participants))
        report.conversations_created = len(conv_hashes)

        typer.echo("\nDry run — no data written to Supabase.")
        report.print_summary()

        typer.echo(f"\n  Unique conversations: {len(conv_hashes)}")
        conv_counts: dict[str, dict[str, Any]] = {}
        for note in notes:
            if not note.participants:
                continue
            p_hash = participant_hash(note.participants)
            if p_hash not in conv_counts:
                conv_counts[p_hash] = {
                    "participants": note.participants,
                    "bursts": 0,
                    "type": note.thread_type,
                }
            conv_counts[p_hash]["bursts"] += 1

        for p_hash, info in sorted(
            conv_counts.items(),
            key=lambda x: -x[1]["bursts"],
        )[:15]:
            participants = ", ".join(p.split("@")[0] for p in info["participants"])
            typer.echo(f"    {info['bursts']:>4} bursts  " f"{info['type']:<10}  {participants}")
        return

    # Real ingestion — wire up clients
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # SupabaseClient
    from pke.supabase_client import SupabaseClient
    from supabase import create_client

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        typer.echo("ERROR: Set SUPABASE_URL and SUPABASE_KEY in .env")
        raise typer.Exit(1)

    supabase_client = SupabaseClient(client=create_client(supabase_url, supabase_key))

    # EmbeddingClient (optional)
    embedding_client = None
    if not no_embed:
        from pke.embedding.openai_client import OpenAIEmbeddingClient

        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            embedding_client = OpenAIEmbeddingClient(openai_key)
            typer.echo("Embedding client: OpenAI")
        else:
            typer.echo("WARNING: OPENAI_API_KEY not set — " "embeddings will be deferred")
    else:
        typer.echo("Embeddings: skipped (--no-embed)")

    # Run ingestion
    from pke.ingestion.yahoo_mail_ingestor import ingest_mbox

    report = ingest_mbox(
        mbox_path=mbox_path,
        supabase_client=supabase_client,
        embedding_client=embedding_client,
        owner_address=owner_address,
        gap_threshold_hours=gap_hours,
        dry_run=False,
    )

    if report.errors:
        typer.echo(f"\n{len(report.errors)} errors occurred.")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
