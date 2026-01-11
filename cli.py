#!/usr/bin/env python3
"""
CLI utility for inspecting and testing parsed Joplin notes.

Usage examples:
  python cli.py --list
  python cli.py --preview --note 2
  python cli.py --upsert --note 0
  python cli.py --search "meeting"

Features:
- Lists all parsed notes with indexes
- Previews a specific note’s content
- Upserts a note to Supabase for testing
- Searches notes by keyword in title or body
"""

import argparse
import json
from pathlib import Path
from typing import Any

from supabase_client import supabase
from parse_joplin_sync import load_resource_metadata, ingest_notes


def load_notes() -> list[dict[str, Any]]:
    """
    Load parsed notes from disk if available, or regenerate them by parsing the Joplin sync folder.

    Returns:
        A list of parsed note dictionaries, each containing metadata, body, and resource links.
    """
    parsed_path = Path("parsed_notes.json")

    if parsed_path.exists():
        with open(parsed_path, "r", encoding="utf-8") as f:
            return json.load(f)

    print("🔄 parsed_notes.json not found. Re-ingesting from sync folder...")

    sync_dir = Path(r"C:\Users\thoma\OneDrive\Apps\Joplin")
    resource_info = load_resource_metadata(sync_dir)
    notes = ingest_notes(sync_dir, resource_info)

    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2, ensure_ascii=False)

    return notes


def list_note_titles(notes: list[dict[str, Any]]) -> None:
    """
    Print a numbered list of all note titles for quick reference.

    Args:
        notes: List of parsed note dictionaries.
    """
    print("📚 Available notes:")
    for i, note in enumerate(notes):
        title = note.get("title", "[no title]")
        print(f"{i:3}: {title}")


def preview_note(note: dict[str, Any]) -> None:
    """
    Print a brief preview of a parsed note.

    Args:
        note: A dictionary representing a parsed note.
    """
    print(f"📝 Title: {note.get('title', '[no title]')}")
    print(f"📎 Resource links: {len(note.get('resource_links', []))}")
    print("📄 Body preview:")
    print(note.get("body", "")[:300] + "...")


def upsert_note(note: dict[str, Any]) -> None:
    """
    Upsert a single note into Supabase.

    Args:
        note: A dictionary representing a parsed note.
    """
    if supabase is None:
        raise RuntimeError("Supabase client is not configured. Check supabase_client.py.")

    payload = {
        "id": note["id"],
        "title": note.get("title", ""),
        "body": note.get("body", ""),
        "metadata": {
            "source_file": note.get("source_file"),
        },
    }

    print(f"🚀 Upserting note {payload['id']} — {payload['title']}")
    supabase.table("notes").upsert(payload).execute()
    print("✅ Upsert complete")


def search_notes(notes: list[dict[str, Any]], keyword: str) -> list[tuple[int, dict[str, Any]]]:
    """
    Search for notes containing the keyword in the title or body.

    Args:
        notes: List of parsed note dictionaries.
        keyword: Keyword to search for (case-insensitive).

    Returns:
        A list of (index, note) tuples where the keyword was found.
    """
    keyword_lower = keyword.lower()
    matches = []

    for i, note in enumerate(notes):
        title = note.get("title", "")
        body = note.get("body", "")
        if keyword_lower in title.lower() or keyword_lower in body.lower():
            matches.append((i, note))

    return matches


if __name__ == "__main__":
    # -------------------------------
    # CLI Argument Parsing
    # -------------------------------
    parser = argparse.ArgumentParser(description="Preview, list, search, or upsert parsed notes")

    parser.add_argument(
        "--list", action="store_true", help="List all parsed note titles with indexes"
    )
    parser.add_argument("--preview", action="store_true", help="Preview a parsed note")
    parser.add_argument("--upsert", action="store_true", help="Upsert a parsed note to Supabase")
    parser.add_argument(
        "--note",
        type=int,
        default=0,
        help="Index of note to preview or upsert (default: 0)",
    )
    parser.add_argument("--search", type=str, help="Search notes by keyword in title or body")

    args = parser.parse_args()

    # -------------------------------
    # Load notes from disk or regenerate
    # -------------------------------
    notes = load_notes()
    if not notes:
        print("⚠️ No notes found.")
        exit(1)

    # -------------------------------
    # Search notes by keyword
    # -------------------------------
    if args.search:
        matches = search_notes(notes, args.search)
        if not matches:
            print(f"🔍 No notes found containing '{args.search}'.")
        else:
            print(f"🔍 Found {len(matches)} matching notes for '{args.search}':")
            for i, note in matches:
                print(f"{i:3}: {note.get('title', '[no title]')}")
        # Exit after search to avoid conflicting actions
        exit(0)

    # -------------------------------
    # List all note titles
    # -------------------------------
    if args.list:
        list_note_titles(notes)

    # -------------------------------
    # Validate note index
    # -------------------------------
    if args.note >= len(notes):
        print(f"⚠️ Note index {args.note} is out of range. Only {len(notes)} notes available.")
        exit(1)

    selected_note = notes[args.note]

    # -------------------------------
    # Preview selected note
    # -------------------------------
    if args.preview:
        print(f"\n🔍 Previewing note #{args.note}:")
        preview_note(selected_note)

    # -------------------------------
    # Upsert selected note
    # -------------------------------
    if args.upsert:
        print(f"\n📤 Upserting note #{args.note} to Supabase:")
        upsert_note(selected_note)

    # -------------------------------
    # Fallback: no action specified
    # -------------------------------
    if not (args.list or args.preview or args.upsert or args.search):
        print(
            "ℹ️ No action specified. Use --list, --preview, --upsert, or "
            "--search to operate on notes."
        )
