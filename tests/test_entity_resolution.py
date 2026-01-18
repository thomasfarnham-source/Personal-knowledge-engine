"""
Unit tests for entity resolution logic.

This test suite will validate the behavior of resolution functions that:
  • Resolve notebook_id from parsed notes
  • Insert missing notebooks, tags, and resources
  • Ensure idempotent behavior and correct upsert ordering

This file currently includes a placeholder test for resolve_notebook_id.
"""

from pke.entity_resolution import resolve_notebook_id


def test_resolve_notebook_id_stub() -> None:
    """
    Verifies that resolve_notebook_id currently returns None.

    This is a placeholder test to anchor future logic. Once implemented,
    this test should be replaced with:
      • Resolution of known notebook titles to UUIDs
      • Insertion of new notebooks and return of generated IDs
      • Handling of missing or malformed notebook fields
    """
    note = {
        "title": "Test Note",
        "notebook": "Test Notebook",  # Expected input field for resolution
    }

    result = resolve_notebook_id(note)

    # Stub behavior: should return None until implemented
    assert result is None
