"""
Unit tests for the sync-folder parser.

These tests exercise every requirement listed in the CURRENT_TASK.md for the
parser exercise. They operate entirely on a small fixture directory under
`tests/test_data/joplin_sync` and therefore do not touch any external system.
"""

import pytest
from pathlib import Path
from pke.parsers.joplin_sync_parser import parse_sync_folder

FIXTURE_DIR = Path(__file__).parent / "test_data" / "joplin_sync"

REQUIRED_FIELDS = {
    "id",
    "title",
    "body",
    "notebook",
    "tags",
    "created_at",
    "updated_at",
    "metadata",
    "source_file",
    "resource_links",
}


def test_parse_returns_list():
    """parse_sync_folder should return a list even with mixed content."""
    result = parse_sync_folder(FIXTURE_DIR)
    assert isinstance(result, list)


def test_all_required_fields_present():
    """Each parsed note must contain exactly the required fields.

    This checks there are no extras and none missing; it also guards
    implicitly against `None` values because such fields would still end up in
    the set of keys but may break other tests.
    """
    notes = parse_sync_folder(FIXTURE_DIR)
    for note in notes:
        assert set(note.keys()) == REQUIRED_FIELDS


def test_notebook_name_resolved_from_parent_id():
    """Note aaaa0001 has its parent_id mapped to the notebook title."""
    notes = parse_sync_folder(FIXTURE_DIR)
    mapping = {n["id"]: n for n in notes}
    assert mapping["aaaa0001"]["notebook"] == "My Test Notebook"


def test_tags_resolved_from_relationships():
    """Tags are pulled from the relationship file via note_tag_map."""
    notes = parse_sync_folder(FIXTURE_DIR)
    mapping = {n["id"]: n for n in notes}
    assert mapping["aaaa0001"]["tags"] == ["my-tag"]


def test_missing_notebook_resolves_to_empty_string():
    """If parent_id is blank the notebook field should be an empty string."""
    notes = parse_sync_folder(FIXTURE_DIR)
    mapping = {n["id"]: n for n in notes}
    assert mapping["aaaa0003"]["notebook"] == ""


def test_missing_tags_resolves_to_empty_list():
    """Notes with no relationships should get an empty tags list."""
    notes = parse_sync_folder(FIXTURE_DIR)
    mapping = {n["id"]: n for n in notes}
    assert mapping["aaaa0002"]["tags"] == []


def test_empty_body_note_included():
    """Notes that have no body text should still appear with an empty string."""
    notes = parse_sync_folder(FIXTURE_DIR)
    mapping = {n["id"]: n for n in notes}
    assert "aaaa0002" in mapping
    assert mapping["aaaa0002"]["body"] == ""


def test_parser_is_deterministic():
    """Repeated invocations on the same directory must yield identical lists."""
    first = parse_sync_folder(FIXTURE_DIR)
    second = parse_sync_folder(FIXTURE_DIR)
    assert first == second


def test_resource_links_extracted():
    """The regex should capture any 32‑hex resource IDs inside the body."""
    notes = parse_sync_folder(FIXTURE_DIR)
    mapping = {n["id"]: n for n in notes}
    assert mapping["aaaa0001"]["resource_links"] == ["abcdef1234567890abcdef1234567890"]


def test_invalid_path_raises_file_not_found():
    """A missing directory should raise FileNotFoundError rather than crash."""
    with pytest.raises(FileNotFoundError):
        parse_sync_folder(Path("/nonexistent/path"))
