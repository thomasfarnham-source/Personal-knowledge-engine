"""
pke/parsers/obsidian_parser.py

Step 1 implementation: vault scanner only.
"""

import os
import logging
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from pke.parsers.obsidian_syntax import strip_obsidian_syntax

logger = logging.getLogger(__name__)


@dataclass
class ParsedNote:
    """ParsedNote contract object emitted by parser builders."""

    id: str
    title: str
    body: str
    notebook: str
    tags: list[str]
    created_at: str
    updated_at: str
    metadata: dict[str, Any]
    source_file: str
    resource_links: list[str]
    source_type: str | None = "obsidian"
    participants: list[str] | None = None
    dominant_sender: str | None = None
    thread_id: str | None = None
    thread_type: str | None = None
    privacy_tier: int | None = 2
    person_ids: list[str] | None = None


@dataclass
class ObsidianParseResult:
    """Structured output for parse_obsidian_vault."""

    notes: list[ParsedNote]
    files_scanned: int
    files_tagged: int
    files_parsed: int
    errors: list[str]


# ─────────────────────────────────────────────────────────────────
# 1. Vault scanner
#
# Walks the vault directory tree and collects all .md file paths.
# Hidden directories (anything starting with ".") are skipped —
# this excludes .obsidian, .trash, and any other dotfiles Obsidian
# or the OS may create.
# ─────────────────────────────────────────────────────────────────


def scan_vault(vault_path: Path) -> list[Path]:
    """
    Walk vault_path and return all .md file paths, skipping hidden directories.

    Hidden directories are those whose name starts with ".". This covers
    .obsidian (plugin data), .trash (deleted notes), and similar dotdirs
    that Obsidian or the OS may create alongside note content.

    Args:
        vault_path: Root directory of the Obsidian vault.

    Returns:
        List of absolute Path objects for every .md file found, in the
        order os.walk() yields them (filesystem order within each directory).
    """
    md_files: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(vault_path):
        # Prune hidden directories in-place so os.walk() won't descend into them
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for filename in filenames:
            if filename.lower().endswith(".md"):
                md_files.append(Path(dirpath) / filename)

    return md_files


# ─────────────────────────────────────────────────────────────────
# 2. Frontmatter reader
#
# Reads YAML frontmatter and markdown body in one call using
# python-frontmatter. Malformed YAML is handled safely so callers can
# skip bad files without crashing the parse run.
# ─────────────────────────────────────────────────────────────────


def read_frontmatter(file_path: Path) -> tuple[dict[str, Any] | None, str]:
    """
    Read a markdown file and return (frontmatter_dict, body_text).

    Returns:
        (frontmatter_dict, body_text) when frontmatter has metadata
        (None, body_text) when frontmatter is absent or empty
        (None, full_content) when YAML is malformed
    """
    try:
        post = frontmatter.load(file_path)
    except (yaml.YAMLError, ValueError) as exc:
        logger.warning("Malformed frontmatter in %s: %s", file_path, exc)
        try:
            return None, file_path.read_text(encoding="utf-8")
        except OSError as read_exc:
            logger.warning("Could not read %s after parse failure: %s", file_path, read_exc)
            return None, ""
    except OSError as exc:
        logger.warning("Could not read %s: %s", file_path, exc)
        return None, ""

    metadata = dict(post.metadata)
    if not metadata:
        return None, post.content

    return metadata, post.content


# ─────────────────────────────────────────────────────────────────
# 3. ParsedNote builder
#
# Converts one opted-in markdown file into a ParsedNote object.
# ----------------------------------------------------------------


def build_parsed_note(
    file_path: Path,
    vault_root: Path,
    frontmatter_dict: dict[str, Any] | None = None,
    body_text: str | None = None,
) -> ParsedNote | None:
    """
    Build one ParsedNote from a vault markdown file.
    Returns None for non-opted-in files or unreadable frontmatter.

    If frontmatter_dict/body_text are provided, they are used directly.
    Otherwise this function reads them from disk via read_frontmatter().
    """
    if frontmatter_dict is None or body_text is None:
        frontmatter_dict, body_text = read_frontmatter(file_path)

    if frontmatter_dict is None:
        return None

    if frontmatter_dict.get("pke-ingest") is not True:
        return None

    cleaned_body = strip_obsidian_syntax(body_text)

    relative_path = file_path.relative_to(vault_root).as_posix()
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
    note_id = f"obsidian::{digest}"

    raw_title = frontmatter_dict.get("pke-title")
    title_candidate = str(raw_title).strip() if raw_title is not None else ""
    title = title_candidate if title_candidate else file_path.stem

    mtime_iso = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat()

    created_at_value = frontmatter_dict.get("created_at")
    if isinstance(created_at_value, datetime):
        created_at = created_at_value.isoformat()
    elif created_at_value is not None:
        created_at = str(created_at_value)
    else:
        created_at = mtime_iso

    updated_at_value = frontmatter_dict.get("updated_at")
    if isinstance(updated_at_value, datetime):
        updated_at = updated_at_value.isoformat()
    elif updated_at_value is not None:
        updated_at = str(updated_at_value)
    else:
        updated_at = mtime_iso

    # Hardcoded label for Reflections panel grouping, consistent with Joplin
    # parser pattern. See milestone 9.9 build log for rationale.
    notebook_value = "Obsidian"

    mapped_keys = {"pke-ingest", "pke-title", "created_at", "updated_at"}
    metadata_value = {
        key: value for key, value in frontmatter_dict.items() if key not in mapped_keys
    }

    return ParsedNote(
        id=note_id,
        title=title,
        body=cleaned_body,
        notebook=notebook_value,
        tags=[],
        created_at=created_at,
        updated_at=updated_at,
        metadata=metadata_value,
        source_file=relative_path,
        resource_links=[],
        source_type="obsidian",
        participants=None,
        dominant_sender=None,
        thread_id=None,
        thread_type=None,
        privacy_tier=2,
        person_ids=None,
    )


# ─────────────────────────────────────────────────────────────────
# 4. Orchestrator
#
# Runs scanner + builder across the vault and returns notes + stats.
# ----------------------------------------------------------------


def parse_obsidian_vault(vault_path: Path) -> ObsidianParseResult:
    """Parse a vault into ParsedNote objects plus counters."""
    notes: list[ParsedNote] = []
    errors: list[str] = []

    md_files = scan_vault(vault_path)
    files_scanned = len(md_files)
    files_tagged = 0
    files_parsed = 0

    for file_path in md_files:
        try:
            frontmatter_dict, body_text = read_frontmatter(file_path)

            if frontmatter_dict is not None and frontmatter_dict.get("pke-ingest") is True:
                files_tagged += 1

            note = build_parsed_note(
                file_path=file_path,
                vault_root=vault_path,
                frontmatter_dict=frontmatter_dict,
                body_text=body_text,
            )
            if note is not None:
                notes.append(note)
                files_parsed += 1

        except OSError as exc:
            errors.append(f"{file_path}: filesystem error: {exc}")
        except ValueError as exc:
            errors.append(f"{file_path}: data error: {exc}")

    return ObsidianParseResult(
        notes=notes,
        files_scanned=files_scanned,
        files_tagged=files_tagged,
        files_parsed=files_parsed,
        errors=errors,
    )
