"""
ingest.py

This script is the entry point for running the ingestion pipeline.

Purpose:
- Provide a simple, explicit way to trigger ingestion from the command line.
- Keep ingestion logic inside pke/ingestion/orchestrator.py (the engine).
- Keep this file focused on orchestration only (the ignition key).

This separation makes the system easier to test, maintain, and extend.
"""

import json
from pathlib import Path
from dotenv import load_dotenv

# SupabaseClient handles:
# - connecting to Supabase
# - resolving notebook IDs
# - generating embeddings
# - upserting notes
from pke.supabase_client import SupabaseClient

# ingest_notes performs the actual ingestion work.
# It lives in pke/ingestion/orchestrator.py to keep logic modular and testable.
from pke.ingestion.orchestrator import ingest_notes

# Load environment variables *after* imports to satisfy flake8 E402.
# This ensures .env variables are available before constructing the client.
load_dotenv()


def main() -> None:
    """
    Main entry point for ingestion.

    Responsibilities:
    - Initialize the Supabase client using environment variables.
    - Load parsed_notes.json from disk.
    - Delegate ingestion to ingest_notes().

    This function intentionally contains no ingestion logic.
    It is purely orchestration.
    """

    # Initialize Supabase client.
    # from_env() keeps secrets out of code and relies on environment variables.
    supabase = SupabaseClient.from_env()

    # Path to parsed_notes.json.
    # This file is produced by the parsing pipeline and acts as a staging artifact.
    parsed_notes_path = Path("parsed_notes.json")

    # Load parsed notes from disk.
    # ingest_notes() expects a List[Dict[str, Any]], not a Path.
    with parsed_notes_path.open("r", encoding="utf-8") as f:
        parsed_notes = json.load(f)

    # Delegate ingestion to the ingestion pipeline.
    # ingest_notes() handles:
    # - notebook resolution
    # - note upserts (with embeddings)
    # - tag extraction and upsert
    # - note‑tag relationship creation
    # - returning a structured summary
    ingest_notes(parsed_notes, supabase)


if __name__ == "__main__":
    # Standard Python entry point guard.
    # Ensures this script runs only when executed directly:
    #   python ingest.py
    main()
