# pke/cli/notes_cli.py

"""
Command‑line interface for interacting with parsed notes.

This module provides entrypoints for:
  • listing notes (future)
  • previewing notes (future)
  • upserting notes into a backend (current focus)

Milestone 7.4:
    The CLI wires into DummyClient to simulate Supabase writes.
    This allows end‑to‑end testing of the ingestion pipeline without
    requiring network access or environment configuration.

Milestone 7.5+:
    The DummyClient will be swapped with a real Supabase client
    implemented in personal_knowledge_engine.supabase.real_client.
"""

import json
from pathlib import Path
import argparse
from typing import Any, List, Dict


def load_parsed_notes() -> List[Dict[str, Any]]:
    """
    Load the parsed notes from the staging artifact `parsed_notes.json`.

    This file is produced earlier in the ingestion pipeline and contains
    normalized note dictionaries ready for upsert.

    Returns
    -------
    list[dict]
        A list of parsed note objects.

    Raises
    ------
    FileNotFoundError
        If the parsed notes file does not exist. This is intentional:
        the CLI should fail loudly when the ingestion pipeline has not
        been run or the file is missing.
    """
    path = Path("parsed_notes.json")

    if not path.exists():
        raise FileNotFoundError("parsed_notes.json not found.")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    """
    Entry point for the Notes CLI.

    This function:
      1. Defines the CLI interface using argparse.
      2. Loads parsed notes from disk.
      3. Dispatches to the appropriate command handler.

    Supported commands:
      • upsert <note_id>   — upsert a single note by ID
      • upsert-all         — upsert all parsed notes

    Notes
    -----
    Additional commands (list, preview, search) will be added in later
    milestones as the ingestion pipeline expands.
    """
    parser = argparse.ArgumentParser(description="Notes CLI")

    # Subcommands container
    subparsers = parser.add_subparsers(dest="command")

    # Command: upsert <note_id>
    upsert_parser = subparsers.add_parser("upsert", help="Upsert a single note by ID")
    upsert_parser.add_argument("note_id", help="The unique note ID to upsert")

    # Command: upsert-all
    subparsers.add_parser("upsert-all", help="Upsert all parsed notes")

    # Parse CLI arguments
    args = parser.parse_args()

    # Load parsed notes from disk
    notes = load_parsed_notes()

    # Command dispatch
    if args.command == "upsert":
        # Find the note with the matching ID
        note = next((n for n in notes if n.get("id") == args.note_id), None)

        if not note:
            print(f"Note {args.note_id} not found.")
            return

        upsert_note(note)

    elif args.command == "upsert-all":
        total = len(notes)
        skipped = 0
        upserted = 0

        for note in notes:
            # ------------------------------------------------------------
            # Milestone 7.4 safeguard:
            # Some parsed objects do not contain an 'id' field because
            # they originate from Joplin items that are not true notes
            # (e.g., type_ = 2 resources, templates, or metadata objects).
            #
            # We skip them during upsert to keep the pipeline running,
            # but we DO NOT discard them. They remain in parsed_notes.json
            # and will be recovered and normalized in Milestone 7.5 when
            # the parser is upgraded to extract IDs and metadata cleanly.
            # ------------------------------------------------------------
            if "id" not in note:
                print(f"⚠️ Skipping malformed note (no id): {note.get('source_file')}")
                skipped += 1
                continue

            upsert_note(note)
            upserted += 1

        # Final summary
        print("\n--- Upsert Summary ---")
        print(f"Total parsed objects: {total}")
        print(f"Valid notes upserted: {upserted}")
        print(f"Malformed notes skipped: {skipped}")


def upsert_note(note: Dict[str, Any]) -> None:
    """
    Upsert a single note using the configured backend client.

    Parameters
    ----------
    note : dict
        A parsed note object containing at minimum:
          • 'id'    — unique identifier
          • 'title' — human-readable title (optional but common)

    Behavior
    --------
    For Milestone 7.4, this function uses DummyClient to simulate
    Supabase writes. This allows the CLI to run end‑to‑end without
    requiring network access or authentication.

    In Milestone 7.5, this function will be updated to select between:
      • DummyClient (dry-run mode)
      • Real Supabase client (production mode)
    """
    # Local import to avoid unnecessary dependency loading when the CLI
    # is used for non-upsert commands (e.g., list, preview).
    from pke.supabase.dummy_client import DummyClient

    client = DummyClient()

    print(f"Upserting note {note['id']}...")
    client.upsert_note(note)


if __name__ == "__main__":
    main()
