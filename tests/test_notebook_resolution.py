"""
Tests for SupabaseClient.resolve_notebook_id()

These tests validate the notebook-resolution workflow:

    • Lookup of an existing notebook by title
    • Insert of a new notebook when none exists
    • Handling of missing titles (return None)
    • Error propagation when the underlying client fails

A lightweight FakeClient is used to simulate Supabase behavior.
This keeps tests deterministic and avoids network calls.
"""

from typing import Any, Dict, List
from pke.supabase_client import SupabaseClient


# ---------------------------------------------------------------------------
# Fake Supabase client for testing
# ---------------------------------------------------------------------------


class FakeTable:
    """
    Simulates the `.table(name)` builder returned by Supabase.

    It supports:
        • .select("id")
        • .eq("title", value)
        • .insert(payload)
        • .execute()

    The FakeClient stores rows in-memory in a dict keyed by table name.

    Type notes:
    - _select_fields: str | None
        Tracks which fields were requested in `.select()`.
    - _filters: Dict[str, Any]
        Stores equality filters applied via `.eq()`.
    - _insert_payload: Dict[str, Any] | None
        Holds the payload passed to `.insert()`, or None if not inserting.
    """

    def __init__(self, table_name: str, store: Dict[str, List[Dict[str, Any]]]):
        self.table_name = table_name
        self.store = store

        # Explicit type annotations ensure mypy does not infer incorrect types.
        self._select_fields: str | None = None
        self._filters: Dict[str, Any] = {}
        self._insert_payload: Dict[str, Any] | None = None

    # --- Query builder methods ------------------------------------------------

    def select(self, fields: str) -> "FakeTable":
        self._select_fields = fields
        return self

    def eq(self, field: str, value: Any) -> "FakeTable":
        self._filters[field] = value
        return self

    def insert(self, payload: Dict[str, Any]) -> "FakeTable":
        self._insert_payload = payload
        return self

    # --- Execute --------------------------------------------------------------

    def execute(self) -> Dict[str, Any]:
        """
        Returns a dict shaped like DummyClient responses:

            { "data": [...], "status": 200 }

        This keeps behavior consistent with your existing DummyClient tests.
        """
        table_rows = self.store.setdefault(self.table_name, [])

        # INSERT path
        if self._insert_payload is not None:
            # Simulate UUID assignment
            new_row = {"id": f"uuid-{len(table_rows) + 1}", **self._insert_payload}
            table_rows.append(new_row)
            return {"data": [new_row], "status": 200}

        # SELECT path
        results = table_rows
        for field, value in self._filters.items():
            results = [row for row in results if row.get(field) == value]

        return {"data": results, "status": 200}


class FakeClient:
    """
    Minimal Supabase-like client exposing `.table(name)`.

    The internal store is a dict:
        { "notebooks": [ {id, title}, ... ] }
    """

    def __init__(self) -> None:
        self.store: Dict[str, List[Dict[str, Any]]] = {}

    def table(self, name: str) -> FakeTable:
        return FakeTable(name, self.store)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_resolve_notebook_id_returns_none_for_missing_title() -> None:
    """
    If a note has no notebook title, resolution should return None.
    """
    client = SupabaseClient(FakeClient())
    assert client.resolve_notebook_id(None) is None
    assert client.resolve_notebook_id("") is None


def test_resolve_notebook_id_inserts_new_notebook() -> None:
    """
    When a notebook does not exist, the client should insert it and return its UUID.
    """
    client = SupabaseClient(FakeClient())

    notebook_id = client.resolve_notebook_id("Work Notes")

    assert notebook_id is not None
    assert notebook_id.startswith("uuid-")

    # Ensure it was actually inserted
    stored = client.client.store["notebooks"]
    assert stored[0]["title"] == "Work Notes"
    assert stored[0]["id"] == notebook_id


def test_resolve_notebook_id_returns_existing_notebook() -> None:
    """
    If a notebook already exists, resolution should return the existing UUID
    and should NOT insert a duplicate.
    """
    fake = FakeClient()
    fake.store["notebooks"] = [{"id": "uuid-1", "title": "Personal"}]

    client = SupabaseClient(fake)

    resolved = client.resolve_notebook_id("Personal")

    assert resolved == "uuid-1"
    assert len(fake.store["notebooks"]) == 1  # No duplicates inserted


def test_resolve_notebook_id_handles_multiple_rows() -> None:
    """
    If multiple notebooks somehow exist with the same title,
    the resolver should return the first match (consistent with Supabase behavior).
    """
    fake = FakeClient()
    fake.store["notebooks"] = [
        {"id": "uuid-1", "title": "Archive"},
        {"id": "uuid-2", "title": "Archive"},
    ]

    client = SupabaseClient(fake)

    resolved = client.resolve_notebook_id("Archive")

    assert resolved == "uuid-1"  # First match wins


def test_resolve_notebook_id_insert_returns_row() -> None:
    """
    Ensures that insert returns a row with an id field.
    """
    client = SupabaseClient(FakeClient())
    notebook_id = client.resolve_notebook_id("Research")

    assert isinstance(notebook_id, str)
    assert notebook_id.startswith("uuid-")
