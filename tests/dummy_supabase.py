"""
DummyClient and FailingClient for local testing of SupabaseClient.

These mocks provide deterministic, fully typed, in‑memory behavior that mirrors
the real Supabase client’s method chain:

    client.table(name).upsert(record).execute()

They allow the ingestion pipeline and SupabaseClient wrapper to be tested
without making real network calls, while implementing SupabaseClientInterface
closely enough to satisfy strict mypy checking and maintain compatibility with
the real WrappedSupabaseClient.

Both clients also implement the `.list()` method used by SupabaseClient,
ensuring end‑to‑end test coverage for read and write operations.
"""

from typing import Any, Dict, List, Optional, cast

from pke.types import (
    UpsertNoteRecord,
    NoteRecord,
    SupabaseClientInterface,
    SupabaseExecuteResponse,
    TableQuery,
)
from pke.supabase_client import Executable

# =====================================================================
# DummyExecuteResponse — simple stand‑in for SupabaseExecuteResponse
# =====================================================================


class DummyExecuteResponse:
    """
    Minimal stand‑in for the response object returned by Supabase `.execute()`.

    Mirrors the shape of SupabaseExecuteResponse:
        • data  — payload returned by the operation
        • error — optional error message
    """

    def __init__(self, data: Any = None, error: Optional[str] = None) -> None:
        self.data = data
        self.error = error


# =====================================================================
# DummyExecutable — returned by DummyTableQuery.upsert()
# =====================================================================


class DummyExecutable(Executable):
    """
    Represents the final `.execute()` call in the Supabase chain.

    DummyTableQuery.upsert() returns an instance of this class. When `.execute()`
    is called, it returns a SupabaseExecuteResponse containing the upserted record.
    """

    def __init__(self, record: UpsertNoteRecord) -> None:
        self.record = record

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """Required to satisfy the Executable Protocol."""
        return None

    def execute(self) -> SupabaseExecuteResponse:
        """
        Execute the request and return a SupabaseExecuteResponse‑compatible object.

        IMPORTANT FOR MYPY:
        --------------------
        Even though `self.record` is structurally identical to UpsertNoteRecord,
        mypy treats it as a plain dict unless we explicitly cast it.

        Without this cast, mypy sees:
            list[dict[str, Any]]
        instead of:
            list[UpsertNoteRecord]

        This is the source of the remaining mypy error in test_supabase_client.py.
        """
        typed = cast(UpsertNoteRecord, self.record)
        resp: SupabaseExecuteResponse = {"status": 200, "data": [typed]}
        return resp


# =====================================================================
# DummyTableQuery — returned by DummyClient.table(name)
# =====================================================================


class DummyTableQuery:
    """
    Simulates the `.upsert()` call on a Supabase table.

    Stores the last upserted record for inspection in tests.
    """

    def __init__(self, table_name: str) -> None:
        self.table_name = table_name
        self.last_upserted: Optional[UpsertNoteRecord] = None

    def upsert(self, record: UpsertNoteRecord) -> DummyExecutable:
        self.last_upserted = record
        return DummyExecutable(record)


# =====================================================================
# DummyClient — Simulates successful Supabase behavior
# =====================================================================


class DummyClient(SupabaseClientInterface):
    """
    Fully typed, deterministic in‑memory mock of SupabaseClientInterface.

    Implements:
        • table(name)
        • upsert(notes)
        • list(query)

    Used to test SupabaseClient without making network calls.
    """

    def __init__(self) -> None:
        self.tables: Dict[str, DummyTableQuery] = {}

    def table(self, name: str) -> DummyTableQuery:
        if name not in self.tables:
            self.tables[name] = DummyTableQuery(name)
        return self.tables[name]

    def upsert(self, notes: List[NoteRecord]) -> SupabaseExecuteResponse:
        """
        Top‑level upsert path.

        This path is used less often in tests, but we still cast to ensure
        strict mypy correctness.
        """
        typed: List[UpsertNoteRecord] = [cast(UpsertNoteRecord, note) for note in notes]
        return {"status": 200, "data": typed}

    def list(self, query: TableQuery) -> List[NoteRecord]:
        # Return a deterministic NoteRecord
        return [
            {
                "id": "dummy-id",
                "content": "dummy content",
                "title": "dummy title",
                "body": "dummy body",
                "metadata": {},
                "embedding": [0.0] * 1536,
            }
        ]


# =====================================================================
# FailingClient — Simulates Supabase errors
# =====================================================================


class FailingClient(SupabaseClientInterface):
    """
    A mock client that always returns an error.

    Used to test error propagation in SupabaseClient.
    """

    def table(self, name: str) -> "FailingTable":
        return FailingTable()

    def upsert(self, notes: List[NoteRecord]) -> SupabaseExecuteResponse:
        return {"status": 500, "data": None}

    def list(self, query: TableQuery) -> List[NoteRecord]:
        raise RuntimeError("Simulated failure")


# =====================================================================
# FailingTable — Returned by FailingClient.table(name)
# =====================================================================


class FailingTable:
    """
    Returned by FailingClient.table(name).

    Its `.upsert()` returns a FailingExecutable.
    """

    def upsert(self, record: NoteRecord) -> "FailingExecutable":
        return FailingExecutable()


# =====================================================================
# FailingExecutable — Returned by FailingTable.upsert(record)
# =====================================================================


class FailingExecutable:
    """
    Returned by FailingTable.upsert(record).

    Its `.execute()` returns an error response.
    """

    def execute(self) -> SupabaseExecuteResponse:
        return {"status": 500, "data": None}

    def __call__(self) -> Any:
        return self
