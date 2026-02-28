"""
fake_test.py

A standalone, developer‑only sanity test for validating the behavior of
SupabaseClient.upsert_note_with_embedding() *without* touching the real
Supabase backend.

This script is intentionally NOT part of the automated pytest suite.
It exists solely for manual verification during development.

What this file validates
------------------------
1. The real SupabaseClient correctly distinguishes:
       • "inserted" on first upsert
       • "updated" on subsequent upserts of the same note ID

2. The client behaves correctly when provided:
       • a fake Supabase client
       • a fake table implementation
       • a precomputed embedding (as the orchestrator would supply)

3. The upsert path works end‑to‑end without requiring:
       • network calls
       • a real Supabase instance
       • the orchestrator

Why this matters
----------------
Your ingestion architecture now requires embeddings to be generated
*outside* the SupabaseClient (by the orchestrator). Therefore, this test
must supply a fake embedding explicitly.

This file ensures the real client’s logic remains correct even when
isolated from the rest of the ingestion pipeline.
"""

from typing import Any, Dict, List

from pke.supabase_client import SupabaseClient


# ---------------------------------------------------------------------------
# Minimal fake Supabase table implementation
# ---------------------------------------------------------------------------
class FakeTable:
    """
    A minimal in‑memory stand‑in for a Supabase table.

    It supports only the operations required by SupabaseClient:
        • select("id").eq("id", value).execute()
        • upsert(record).execute()

    The goal is not to simulate Supabase perfectly, but to provide just
    enough behavior for deterministic testing.
    """

    def __init__(self, storage: Dict[str, Dict[str, Any]]) -> None:
        # Shared dict across all FakeTable instances for this FakeClient.
        self.storage = storage
        self._query_id: str | None = None

    def select(self, field: str) -> "FakeTable":
        # Real Supabase returns a query builder; we simply return self.
        return self

    def eq(self, field: str, value: str) -> "FakeTable":
        # Store the queried ID so execute() can return the correct result.
        self._query_id = value
        return self

    def execute(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Simulate Supabase's return shape:

            {"data": [{"id": ...}]}   if record exists
            {"data": []}              if not found
        """
        if self._query_id in self.storage:
            return {"data": [{"id": self._query_id}]}
        return {"data": []}

    def upsert(self, record: Dict[str, Any]) -> "FakeTable":
        """
        Simulate Supabase upsert behavior:
            • Insert if new
            • Overwrite if existing
        """
        self.storage[record["id"]] = record
        return self


# ---------------------------------------------------------------------------
# Minimal fake Supabase client
# ---------------------------------------------------------------------------
class FakeClient:
    """
    A minimal fake Supabase client exposing only .table(name).

    All tables share the same underlying storage dict, which allows
    FakeTable to simulate existence checks and upserts.
    """

    def __init__(self) -> None:
        self.storage: Dict[str, Dict[str, Any]] = {}

    def table(self, name: str) -> FakeTable:
        return FakeTable(self.storage)


# ---------------------------------------------------------------------------
# Instantiate the real SupabaseClient with our fake backend
# ---------------------------------------------------------------------------
client = SupabaseClient(
    dry_run=False,  # Force real-mode logic (existence checks, upserts)
    client=FakeClient(),  # Inject our fake Supabase backend
)

# A deterministic fake embedding (the orchestrator would normally generate this)
FAKE_EMBEDDING: List[float] = [0.0] * 1536


# ---------------------------------------------------------------------------
# First call → should be "inserted"
# ---------------------------------------------------------------------------
action1: Any = client.upsert_note_with_embedding(
    id="abc123",
    title="Hello",
    body="World",
    metadata={},  # Minimal metadata for this test
    notebook_id=None,  # No notebook resolution needed here
    embedding=FAKE_EMBEDDING,
)
print("First call:", action1)  # Expect: "inserted"


# ---------------------------------------------------------------------------
# Second call → should be "updated"
# ---------------------------------------------------------------------------
action2: Any = client.upsert_note_with_embedding(
    id="abc123",
    title="Hello again",
    body="World again",
    metadata={},
    notebook_id=None,
    embedding=FAKE_EMBEDDING,
)
print("Second call:", action2)  # Expect: "updated"
