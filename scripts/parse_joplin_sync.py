import json
import mimetypes
import os
from pathlib import Path
import re
from typing import Any

import psutil

# === CONFIGURATION ===
# Define the path to your Joplin sync directory.
# This is where all your .md note files and .resource files live.
SYNC_DIR = Path(r"C:\Users\thoma\OneDrive\Apps\Joplin")
RESOURCE_DIR = SYNC_DIR / ".resource"


# === MEMORY MONITORING ===
def print_memory_usage(label: str = "") -> None:
    """
    Print current memory usage in MB with a label.
    Useful for tracking memory growth during ingestion.
    """
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / (1024 * 1024)
    print(f"🧠 Memory usage {label}: {mem_mb:.2f} MB")


# === FILE LOADERS ===
def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file and return its contents as a Python dictionary."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_markdown(path: Path) -> str:
    """Load a Markdown (.md) file and return its full text as a string."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# === NOTE CLASSIFICATION ===
def is_note_like_type_1(md_text: str) -> bool:
    """
    Heuristic to detect Evernote-imported notes (type_: 1) that lack front matter.
    These notes typically contain 'id:', 'created_time:', and 'source: evernote'.
    """
    return "id: " in md_text and "created_time: " in md_text and "source: evernote" in md_text


# === EXTENSION RESOLUTION ===
def resolve_extension(mime_type: str) -> str:
    """
    Given a MIME type (e.g., 'image/png'), return the corresponding file extension (e.g., '.png').
    """
    ext = mimetypes.guess_extension(mime_type)
    return ext if ext else ""


# === RESOURCE METADATA LOADER ===
def load_resource_metadata(sync_dir: Path) -> dict[str, dict[str, str]]:
    """
    Load all .resource-*.md metadata files and return a dictionary:
    { resource_id: { 'mime': ..., 'extension': ... } }
    """
    resource_meta: dict[str, dict[str, str]] = {}
    for meta_file in sync_dir.glob(".resource-*.md"):
        try:
            meta = load_json(meta_file)
            rid = meta.get("id")
            mime = meta.get("mime")
            if rid and mime:
                resource_meta[rid] = {
                    "mime": mime,
                    "extension": resolve_extension(mime),
                }
        except Exception as e:
            print(f"⚠️ Failed to parse {meta_file.name}: {e}")
    return resource_meta


# === RESOURCE LINK EXTRACTOR ===
def extract_resource_links(markdown_body: str) -> list[str]:
    """
    Extract resource IDs from Markdown links like ![](:/resource_id).
    Returns a list of 32-character hex strings.
    """
    return re.findall(r"\(:/([a-f0-9]{32})\)", markdown_body)


# === TYPE 2 NOTE PARSER ===
def parse_front_matter(md_text: str) -> dict[str, Any]:
    """
    Parse YAML-style front matter from type_: 2 notes.
    Returns a dictionary with metadata and a 'body' field.
    """
    lines = md_text.splitlines()
    meta: dict[str, Any] = {}
    body_lines = []
    in_meta = True
    for line in lines:
        if in_meta and ": " in line:
            key, val = line.split(": ", 1)
            meta[key.strip()] = val.strip()
        else:
            in_meta = False
            body_lines.append(line)
    meta["body"] = "\n".join(body_lines).strip()
    return meta


# === TYPE 1 EVERNOTE NOTE PARSER ===
def parse_evernote_note(md_text: str) -> dict[str, Any]:
    """
    Parse Evernote-imported type_: 1 notes.
    - Title = first non-empty line
    - Body = all content before metadata block
    - Metadata = lines starting with 'id:'
    """
    lines = md_text.splitlines()
    meta: dict[str, Any] = {}
    content_lines = []
    metadata_lines = []

    # Split content and metadata
    in_metadata = False
    for line in lines:
        if re.match(r"^\s*id: ", line):
            in_metadata = True
        if in_metadata:
            metadata_lines.append(line)
        else:
            content_lines.append(line)

    # Extract title and body
    content_lines = [line.strip() for line in content_lines if line.strip()]
    title = content_lines[0] if content_lines else ""
    body = "\n".join(content_lines[1:]) if len(content_lines) > 1 else ""

    # Parse metadata block
    for line in metadata_lines:
        if ": " in line:
            key, val = line.split(": ", 1)
            meta[key.strip()] = val.strip()

    meta["title"] = title
    meta["body"] = body
    return meta


# === NOTE INGESTION ===
def ingest_notes(sync_dir: Path, resource_info: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    """
    Scan all .md files in the sync folder and subfolders.
    - Parse type_: 2 notes with front matter
    - Parse type_: 1 Evernote notes with inferred structure
    - Extract resource links and enrich with MIME/extension
    """
    notes: list[dict[str, Any]] = []
    type1_count = 0
    type2_count = 0
    skipped = 0

    for md_file in sync_dir.rglob("*.md"):
        if md_file.name.startswith(".resource-"):
            continue  # Skip resource metadata files
        text = load_markdown(md_file)
        if "type_: 2" in text:
            meta = parse_front_matter(text)
            type2_count += 1
        elif is_note_like_type_1(text):
            meta = parse_evernote_note(text)
            type1_count += 1
        else:
            skipped += 1
            continue
        meta["source_file"] = str(md_file)
        meta["resource_links"] = extract_resource_links(meta.get("body", ""))
        meta["resource_files"] = [
            {
                "id": rid,
                "extension": resource_info.get(rid, {}).get("extension", ""),
                "mime": resource_info.get(rid, {}).get("mime", ""),
            }
            for rid in meta["resource_links"]
        ]
        notes.append(meta)

    # Print summary of ingestion
    print(f"📘 Parsed {type2_count} type_: 2 notes")
    print(f"📗 Parsed {type1_count} Evernote notes")
    print(f"🚫 Skipped {skipped} files")
    return notes


# === MAIN EXECUTION ===
if __name__ == "__main__":
    # Step 1: Load resource metadata
    print("📦 Loading resource metadata...")
    resource_info = load_resource_metadata(SYNC_DIR)
    print(f"✅ Loaded metadata for {len(resource_info)} resources")

    # Step 2: Ingest notes
    print_memory_usage("before ingestion")
    print("📥 Ingesting notes...")
    notes = ingest_notes(SYNC_DIR, resource_info)
    print_memory_usage("after ingestion")

    print(f"✅ Loaded {len(notes)} notes")
    with_resources = sum(1 for n in notes if n["resource_links"])
    print(f"📎 Notes with resource links: {with_resources}")

    # Step 3: Preview first 2 notes for sanity check
    print("\n🔎 Previewing first 2 parsed notes:")
    for i, note in enumerate(notes[:2], 1):
        print(f"\n--- Note {i} ---")
        print(json.dumps(note, indent=2))

    # Step 4: Export all parsed notes to JSON
    # This will overwrite 'parsed_notes.json' on each run
    with open("parsed_notes.json", "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2, ensure_ascii=False)
