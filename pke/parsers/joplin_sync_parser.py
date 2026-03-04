import re
import logging
from pathlib import Path
from collections import defaultdict

# ---------------------------------------------------------------------------
# Parser for Joplin sync-folder export
# ---------------------------------------------------------------------------
# This module contains a stand-alone parser that consumes the raw markdown
# files exported by Joplin's sync folder. It replaces the deprecated
# Markdown-export parser; the former file (`joplin_markdown.py`) should never
# be used or referenced.
#
# The parser is built in three clearly defined passes:
#   1. Load & classify: read every .md file, pulling out structural
#      information and the embedded metadata block.
#   2. Build lookup maps: construct dictionaries for notebooks, tags, and
#      note-tag relationships based solely on the classified records.
#   3. Enrich notes: take the raw note records and resolve foreign keys,
#      apply normalization, and emit the final `ParsedNote` contract.
#
# Each function is written to be deterministic (no random choices, no
# shared mutable state) and side-effect-free except for logging warnings.
# This makes it trivial to unit-test and ensures repeated runs produce
# identical output.
# ---------------------------------------------------------------------------

# regex for extracting Joplin resource links; links in the body are
# always wrapped in parentheses as part of Markdown syntax:
#   (:/<32hex>)
RESOURCE_RE = re.compile(r"\(:/([a-f0-9]{32})\)")
# simple pattern matching "key: value" lines used in metadata blocks
META_LINE_RE = re.compile(r"^([^:]+):(.*)$")


def parse_sync_folder(sync_dir: Path) -> list[dict]:
    """
    Main entry point. Runs all three passes and returns a list
    of ParsedNote dicts conforming to the output contract.

    Args:
        sync_dir: Path to the Joplin sync folder.

    Returns:
        List of ParsedNote dicts, sorted by id.

    Raises:
        FileNotFoundError: if sync_dir does not exist.
        ValueError: if sync_dir contains no .md files.
    """

    # ensure the caller gave us a valid directory
    if not sync_dir.exists():
        raise FileNotFoundError(f"Sync directory {sync_dir} does not exist")

    # pass 1: read and classify every file in the directory
    raw_files = _load_all_files(sync_dir)
    # if there were no markdown files at all, signal an error instead of
    # returning an empty list; caller may treat empty as success.
    if not any(raw_files.values()):
        raise ValueError(f"No markdown files found in {sync_dir}")

    # pass 2: build lookup dictionaries that the final step will use
    notebook_map, tag_map, note_tag_map = _build_lookup_maps(raw_files)
    # pass 3: build the final ParsedNote objects from raw notes (type "1")
    notes = _enrich_notes(raw_files.get("1", []), notebook_map, tag_map, note_tag_map)
    return notes


# ---------------------------------------------------------------------------
# Pass 1 helpers
# ---------------------------------------------------------------------------


def _parse_md_file(file_path: Path) -> dict:
    """
    Parse a single .md file into a raw dictionary.

    Structure:
        - First line = name or title
        - Blank line separates title from body (notes only)
        - Lines before metadata block = body (notes only)
        - Metadata block = key: value pairs
        - type_ is always present in metadata

    Returns:
        Raw dict with all parsed fields including type_.
        source_file is set to the absolute path string.
    """
    # read file contents; if this fails we log a warning and return
    # a stub record with type_ "0" so that callers can skip it.
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logging.warning(f"Failed to read {file_path}: {e}")
        return {"type_": "0"}

    lines = text.splitlines()
    if not lines:
        # completely empty file
        logging.warning(f"Empty file {file_path}")
        return {"type_": "0"}

    # first line is always the title/name of the note/notebook/tag
    title = lines[0].strip()

    # identify metadata block by walking backwards through the file
    # looking for consecutive "key: value" lines. This heuristic handles
    # cases where the body may contain colons; the metadata block is assumed
    # to be the final contiguous block of such lines in the file.
    meta_lines = []
    for line in reversed(lines[1:]):  # skip title
        if META_LINE_RE.match(line):
            meta_lines.append(line)
        else:
            break
    meta_lines.reverse()

    body_lines = []
    if meta_lines:
        # metadata starts at index of first meta line; everything between
        # the title and that index is body text.
        start_idx = len(lines) - len(meta_lines)
        body_lines = lines[1:start_idx]
    else:
        # no metadata detected; conservatively treat the remainder as body
        body_lines = lines[1:]

    body = "\n".join(body_lines).strip()

    # parse each metadata line into key/value pairs. we deliberately do not
    # eval or interpret the values; they remain strings (empty if missing).
    metadata = {}
    for m in meta_lines:
        m = m.rstrip()
        m_match = META_LINE_RE.match(m)
        if not m_match:
            continue
        key = m_match.group(1).strip()
        value = m_match.group(2).strip()
        metadata[key] = value

    # assemble the final raw dictionary. include the absolute path so tests
    # and consumers can trace back the origin.
    result: dict = {"title": title, "body": body, "source_file": str(file_path.resolve())}
    result.update(metadata)
    # ensure type_ exists even if not parsed (malformed file)
    if "type_" not in result:
        result["type_"] = "0"

    return result


def _load_all_files(sync_dir: Path) -> dict[str, list[dict]]:
    """
    Pass 1: Read and classify all .md files.

    Returns:
        Dict keyed by type_ string, each value is a list
        of raw parsed dicts for that type.
    """
    # iterate only the top-level entries in the directory; Joplin sync
    # exports are flat. ignore subdirectories.
    # use full type parameters to satisfy mypy
    files_by_type: defaultdict[str, list[dict]] = defaultdict(list)
    for child in sync_dir.iterdir():
        if child.is_file() and child.suffix.lower() == ".md":
            parsed = _parse_md_file(child)
            # skip files that failed to parse or have no type_
            if not parsed or "type_" not in parsed:
                continue
            t = str(parsed.get("type_", ""))
            if t == "":
                continue
            files_by_type[t].append(parsed)
    # return a plain dict for callers
    return dict(files_by_type)


# ---------------------------------------------------------------------------
# Pass 2 helper
# ---------------------------------------------------------------------------


def _build_lookup_maps(
    raw_files: dict[str, list[dict]],
) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    """
    Pass 2: Build resolution maps from classified files.

    Returns:
        notebook_map:  {notebook_id: notebook_name}
        tag_map:       {tag_id: tag_name}
        note_tag_map:  {note_id: [tag_ids]}
    """
    # maps are built fresh on every call; no reuse of mutable state
    notebook_map: dict[str, str] = {}
    tag_map: dict[str, str] = {}
    note_tag_map: dict[str, list[str]] = {}

    # notebooks (type 2): id -> title
    for note in raw_files.get("2", []):
        nid = note.get("id", "")
        name = note.get("title", "")
        if nid:
            notebook_map[nid] = name

    # tags (type 5): id -> title
    for tag in raw_files.get("5", []):
        tid = tag.get("id", "")
        name = tag.get("title", "")
        if tid:
            tag_map[tid] = name

    # relationships (type 6): note_id -> list of tag_id
    for rel in raw_files.get("6", []):
        note_id = rel.get("note_id", "")
        tag_id = rel.get("tag_id", "")
        # gracefully skip malformed entries
        if not note_id or not tag_id:
            continue
        note_tag_map.setdefault(note_id, []).append(tag_id)

    return notebook_map, tag_map, note_tag_map


# ---------------------------------------------------------------------------
# Pass 3 helper
# ---------------------------------------------------------------------------


def _enrich_notes(
    raw_notes: list[dict],
    notebook_map: dict[str, str],
    tag_map: dict[str, str],
    note_tag_map: dict[str, list[str]],
) -> list[dict]:
    """
    Pass 3: Resolve and normalize raw notes into ParsedNote dicts.

    Returns:
        List of ParsedNote dicts, sorted by id.
    """
    # convert a list of raw note dicts into the final ParsedNote schema
    enriched: list[dict] = []

    for note in raw_notes:
        # encrypted notes are skipped entirely; we log but do not raise
        if note.get("encryption_applied") == "1":
            nid = note.get("id", "<unknown>")
            logging.warning(f"Skipping encrypted note {nid}")
            continue

        # basic field extraction with defaults
        nid = str(note.get("id", ""))
        title = note.get("title", "")
        body = note.get("body", "")
        parent = note.get("parent_id", "")
        notebook_name = notebook_map.get(parent, "") if parent else ""

        # resolve tags: map note_id -> [tag_id] -> [tag_name]
        tag_ids = note_tag_map.get(nid, [])
        tags = [tag_map.get(tid, "") for tid in tag_ids if tid in tag_map]

        created = note.get("created_time", "") or ""
        updated = note.get("updated_time", "") or ""

        # metadata includes any raw keys not part of the canonical contract
        reserved = {
            "id",
            "title",
            "body",
            "parent_id",
            "created_time",
            "updated_time",
            "encryption_applied",
            "source_file",
            "type_",
        }
        metadata = {}
        for k, v in note.items():
            if k in reserved:
                continue
            metadata[k] = v if v is not None else ""

        parsed = {
            "id": nid,
            "title": title or "",
            "body": body or "",
            "notebook": notebook_name,
            "tags": tags,
            "created_at": created,
            "updated_at": updated,
            "metadata": metadata,
            "source_file": note.get("source_file", ""),
            "resource_links": _extract_resource_links(body),
        }

        # ensure no None values remain
        for key, val in parsed.items():
            if val is None:
                parsed[key] = "" if isinstance(val, str) else []

        enriched.append(parsed)

    # final determinism: sort lexicographically by id
    enriched.sort(key=lambda x: x.get("id", ""))
    return enriched


def _extract_resource_links(body: str) -> list[str]:
    """
    Extract Joplin resource IDs from body content.
    Pattern: (:/<resource_id>) where resource_id is a 32-char hex string.

    Returns:
        List of resource ID strings. Empty list if none found.
    """
    # if body is empty or None, just return an empty list
    if not body:
        return []
    return RESOURCE_RE.findall(body)
