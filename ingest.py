"""
ingest.py

This script is the entry point for running the ingestion pipeline.

Purpose:
- Provide a simple, explicit way to trigger ingestion from the command line.
- Keep ingestion logic inside pke/ingestion.py (the engine).
- Keep this file focused on orchestration only (the ignition key).

This separation makes the system easier to test, maintain, and extend.
"""

from pathlib import Path
from dotenv import load_dotenv

# SupabaseClient handles:
# - connecting to Supabase
# - resolving notebook IDs
# - generating embeddings
# - upserting notes
from pke.supabase_client import SupabaseClient

# ingest_all_notes performs the actual ingestion work.
# It lives in pke/ingestion.py to keep logic modular and testable.
from pke.ingestion import ingest_all_notes

# Load environment variables *after* imports to satisfy flake8 E402.
# This call has no side effects on import order or module structure.
load_dotenv()


def main() -> None:
    """
    Main entry point for ingestion.

    Responsibilities:
    - Initialize the Supabase client using environment variables.
    - Define the path to parsed_notes.json.
    - Delegate ingestion to ingest_all_notes().

    This function intentionally contains no ingestion logic.
    It is purely orchestration.
    """

    # Initialize Supabase client.
    supabase = SupabaseClient.from_env()

    # Path to parsed_notes.json.
    parsed_notes_path = Path("parsed_notes.json")

    # Delegate ingestion to the ingestion pipeline.
    ingest_all_notes(parsed_notes_path, supabase)


if __name__ == "__main__":
    main()
