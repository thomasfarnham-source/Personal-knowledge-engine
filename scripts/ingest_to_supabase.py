#!/usr/bin/env python3
"""
Ingest parsed Joplin notes into Supabase.

Features:
- --reset: optionally clear the notes table before ingesting (with confirmation)
- --dry-run: simulate ingestion without writing to Supabase
- --limit N: ingest only the first N notes (useful for fast testing)
- --log-to FILE: append a JSON run summary (metadata, counts, failures) to FILE
- Uses upsert so repeated runs do not create duplicates
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from supabase_client import supabase  # Assumes you have a configured Supabase client

# -------------------------
# CLI argument parsing
# -------------------------
parser = argparse.ArgumentParser(description="Ingest parsed notes into Supabase")
parser.add_argument(
    "--reset",
    action="store_true",
    help="Clear Supabase notes table before ingesting (requires confirmation)",
)
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Simulate ingestion without writing to Supabase",
)
parser.add_argument("--limit", type=int, help="Only ingest the first N notes (useful for testing)")
parser.add_argument(
    "--log-to",
    type=str,
    help="Append a JSON run summary to the specified file (e.g., run_log.json)",
)
args = parser.parse_args()

# -------------------------
# Optional reset behavior
# -------------------------
if args.reset:
    confirm = input("⚠️  This will DELETE all existing notes in Supabase. Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("❌ Reset cancelled. No data was deleted.")
        exit(0)

    if supabase is None:
        raise RuntimeError("Supabase client is not configured")

    print("🧹 Clearing existing notes from Supabase...")
    supabase.table("notes").delete().neq("id", "").execute()
    print("✅ Notes table cleared")

# -------------------------
# Load parsed notes JSON
# -------------------------
parsed_path = Path("parsed_notes.json")
if not parsed_path.exists():
    raise FileNotFoundError("parsed_notes.json not found. Run parse_joplin_sync.py first.")

with open(parsed_path, "r", encoding="utf-8") as parsed_file:
    notes: list[dict[str, Any]] = json.load(parsed_file)

if args.limit:
    notes = notes[: args.limit]
    print(f"📥 Loaded first {len(notes)} notes (limit={args.limit}) from parsed_notes.json")
else:
    print(f"📥 Loaded {len(notes)} notes from parsed_notes.json")

# -------------------------
# Ingest loop
# -------------------------
success_count = 0
failures: list[dict[str, str]] = []
start_time = datetime.utcnow().isoformat() + "Z"

for note in notes:
    try:
        payload = {
            "id": note["id"],
            "title": note.get("title", ""),
            "body": note.get("body", ""),
            "created_time": note.get("created_time"),
            "updated_time": note.get("updated_time"),
            "source": note.get("source"),
            "source_application": note.get("source_application"),
            "resource_links": note.get("resource_links", []),
            "resource_files": note.get("resource_files", []),
            "metadata": {
                "author": note.get("author"),
                "latitude": note.get("latitude"),
                "longitude": note.get("longitude"),
                "altitude": note.get("altitude"),
                "parent_id": note.get("parent_id"),
                "source_file": note.get("source_file"),
            },
        }

        if args.dry_run:
            print(f"🧪 [Dry Run] Would upsert note: {payload['id']} — {payload['title']}")
        else:
            if supabase is None:
                raise RuntimeError("Supabase client is not configured")
            supabase.table("notes").upsert(payload).execute()
            success_count += 1

    except Exception as e:
        failures.append({"id": str(note.get("id", "unknown")), "error": str(e)})

# -------------------------
# Summary and reporting
# -------------------------
end_time = datetime.utcnow().isoformat() + "Z"
if args.dry_run:
    print(f"\n🧪 Dry run complete. Simulated {len(notes)} upserts.")
else:
    print(f"\n✅ Ingested {success_count} notes into Supabase")

if failures:
    print(f"❌ {len(failures)} notes failed to ingest:")
    for failure in failures[:5]:
        print(f"  - {failure['id']}: {failure['error']}")
    if len(failures) > 5:
        print(f"  ...and {len(failures) - 5} more")

# -------------------------
# Optional: write run log to file (--log-to)
# -------------------------
if args.log_to:
    run_summary = {
        "run_started_at": start_time,
        "run_finished_at": end_time,
        "dry_run": bool(args.dry_run),
        "limit": args.limit if args.limit is not None else "none",
        "reset": bool(args.reset),
        "notes_processed": len(notes),
        "notes_ingested": success_count if not args.dry_run else 0,
        "failures_count": len(failures),
        "failures_sample": failures[:10],
    }

    try:
        with open(args.log_to, "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(run_summary, ensure_ascii=False) + "\n")
        print(f"📝 Run summary appended to {args.log_to}")
    except Exception as e:
        print(f"⚠️  Failed to write run log to {args.log_to}: {e}")
