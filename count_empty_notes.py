import json
from pathlib import Path

parsed_notes_path = Path("parsed_notes.json")

with parsed_notes_path.open("r", encoding="utf-8") as f:
    notes = json.load(f)

empty = []
for note in notes:
    body = note.get("body", "")
    if body is None or str(body).strip() == "":
        empty.append(note)

print(f"Total notes: {len(notes)}")
print(f"Notes with empty bodies: {len(empty)}\n")

print("Titles of notes with empty bodies:")
for note in empty:
    title = note.get("title", "<no title>")
    print(f"- {title}")