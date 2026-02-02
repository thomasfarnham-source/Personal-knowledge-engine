import pytest  # noqa: F401
from pathlib import Path
from pke.parsers.joplin_markdown import parse_note


# ---------------------------------------------------------------------------
# Helper: load fixture files from tests/fixtures/
# ---------------------------------------------------------------------------
def load_fixture(name: str) -> Path:
    """
    Returns the full path to a fixture Markdown file.
    """
    base = Path(__file__).parent.parent / "fixtures"
    return base / name


# ---------------------------------------------------------------------------
# 1. Basic metadata parsing
# ---------------------------------------------------------------------------
def test_parse_basic_note():
    """
    Validates that a simple Markdown note with minimal metadata is parsed
    correctly. Ensures that YAML frontmatter and body extraction work.
    """
    path = load_fixture("note_basic.md")
    parsed = parse_note(path)

    assert parsed["id"] == "note-basic-1234"
    assert parsed["title"] == "Basic Test Note"
    assert parsed["notebook"] == "Test Notebook"
    assert parsed["tags"] == []
    assert parsed["created_time"] == 1704067200000
    assert parsed["updated_time"] == 1704068200000

    # Body should be extracted cleanly
    assert "This is a simple test note." in parsed["body"]


# ---------------------------------------------------------------------------
# 2. Tag extraction
# ---------------------------------------------------------------------------
def test_parse_note_with_tags():
    """
    Ensures that tag lists are parsed correctly from YAML frontmatter.
    """
    path = load_fixture("note_with_tags.md")
    parsed = parse_note(path)

    assert parsed["id"] == "note-tags-5678"
    assert parsed["title"] == "Note With Tags"
    assert parsed["notebook"] == "Tagged Notebook"

    # Tags should be parsed as a list of strings
    assert parsed["tags"] == ["personal", "work", "ideas"]


# ---------------------------------------------------------------------------
# 3. Resource reference extraction
# ---------------------------------------------------------------------------
def test_parse_note_with_resources():
    """
    Ensures that resource IDs (:/abcdef...) are extracted from the body.
    """
    path = load_fixture("note_with_resources.md")
    parsed = parse_note(path)

    assert parsed["id"] == "note-resources-9999"
    assert parsed["title"] == "Note With Resources"
    assert parsed["tags"] == ["attachments"]

    # Resource IDs should be extracted from the body
    assert parsed["resources"] == [
        "abc123def4567890",
        "9999aaaabbbbcccc",
    ]


# ---------------------------------------------------------------------------
# 4. Missing metadata fields
# ---------------------------------------------------------------------------
def test_parse_note_missing_fields():
    """
    Ensures that missing YAML fields do not break parsing and that the parser
    applies correct defaults (e.g., None or empty lists).
    """
    path = load_fixture("note_missing_fields.md")
    parsed = parse_note(path)

    assert parsed["id"] == "note-missing-0001"

    # Missing fields should be None or empty depending on parser design
    assert parsed.get("title") in (None, "")
    assert parsed.get("updated_time") in (None, 0)
    assert parsed.get("tags") in (None, [], ())
    assert parsed.get("notebook") in (None, "")

    # Body should still be extracted
    assert "missing several metadata fields" in parsed["body"]
