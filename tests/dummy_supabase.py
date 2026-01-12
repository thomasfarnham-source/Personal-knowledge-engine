"""
DummyClient and FailingClient for local testing of SupabaseClient.

These mocks implement SupabaseClientInterface exactly, ensuring:
    - deterministic behavior in tests,
    - strict mypy compliance,
    - and compatibility with the real WrappedSupabaseClient.

They simulate the method chain:
    client.table(name).upsert(record).execute()

and the `.list()` method used by SupabaseClient.
"""

from typing import Any, Dict, List, Optional

from pke.types import (
    NoteRecord,
    SupabaseClientInterface,
    SupabaseExecuteResponse,
    TableQuery,
)


# =====================================================================
# DummyClient — Simulates successful Supabase behavior
# =====================================================================

class DummyClient(SupabaseClientInterface):
    """
    A fully typed, deterministic mock Supabase client.

    Implements the entire SupabaseClientInterface:
        - table(name)
        - upsert(notes)
        - list(query)

    Used to test SupabaseClient without making network calls.
    """

    def __init__(self) -> None:
        # Store table objects so tests can inspect what was upserted
        self.tables: Dict[str, DummyTableQuery] = {}

    def table(self, name: str) -> "DummyTableQuery":
        """
        Return a DummyTableQuery for the given table name.
        """
        if name not in self.tables:
            self.tables[name] = DummyTableQuery(name)
        return self.tables[name]

    def upsert(self, notes: List[NoteRecord]) -> SupabaseExecuteResponse:
        """
        Simulate a successful upsert.

        The real wrapped client returns:
            {"status": int, "data": Any}

        So we return the same structure.
        """
        return {
            "status": 200,
            "data": notes,
        }

    def list(self, query: TableQuery) -> List[NoteRecord]:
        """
        Simulate a successful list query.

        Returns a deterministic dummy NoteRecord so tests can rely on it.
        """
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
# DummyTableQuery — Returned by DummyClient.table(name)
# =====================================================================

class DummyTableQuery:
    """
    Simulates the object returned by `.table(name)` in the real client.

    Supports:
        - .upsert(record) → DummyExecutable
    """

    def __init__(self, table_name: str):
        self.table_name = table_name
        self.last_upserted: Optional[NoteRecord] = None

    def upsert(self, record: NoteRecord) -> "DummyExecutable":
        """
        Store the record for inspection and return an executable object.
        """
        self.last_upserted = record
        return DummyExecutable(record)


# =====================================================================
# DummyExecutable — Returned by DummyTableQuery.upsert(record)
# =====================================================================

class DummyExecutable:
    """
    Simulates the final `.execute()` call in the Supabase chain.

    The real wrapped client returns:
        {"status": int, "data": Any}

    So this mock returns the same structure.
    """

    def __init__(self, record: NoteRecord):
        self.record = record

    def execute(self) -> SupabaseExecuteResponse:
        """
        Return a successful SupabaseExecuteResponse containing the record.
        """
        return {
            "status": 200,
            "data": [self.record],
        }

    def __call__(self) -> Any:
        """
        Executable protocol requires __call__ to exist.

        Returning self is harmless and satisfies the protocol.
        """
        return self


# =====================================================================
# FailingClient — Simulates Supabase errors
# =====================================================================

class FailingClient(SupabaseClientInterface):
    """
    A mock client that always returns an error.

    Used to test error propagation in SupabaseClient.
    """

    def table(self, name: str) -> "FailingTable":
        """
        Always return a failing table object.
        """
        return FailingTable()

    def upsert(self, notes: List[NoteRecord]) -> SupabaseExecuteResponse:
        """
        Simulate a failing upsert.

        Note: SupabaseExecuteResponse TypedDict only includes "status" and "data".
        We return a 500 status and None data to indicate failure.
        """
        return {
            "status": 500,
            "data": None,
        }

    def list(self, query: TableQuery) -> List[NoteRecord]:
        """
        Simulate a failing list operation.
        """
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
        # Return the minimal SupabaseExecuteResponse shape for failure.
        return {
            "status": 500,
            "data": None,
        }

    def __call__(self) -> Any:
        return self
