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

from typing import Any, Dict, List, Optional, Union, cast

from pke.types import (
    NoteRecord,
    SupabaseClientInterface,
    SupabaseExecuteResponse,
    TableQuery,
)
from pke.types import Executable

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

    def __init__(self, record: Dict[str, Any]) -> None:
        self.record = record

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """Required to satisfy the Executable Protocol."""
        return None

    def execute(self) -> SupabaseExecuteResponse:
        """
        Execute the request and return a SupabaseExecuteResponse‑compatible object.

        The record is returned inside a list to match the real Supabase client's
        behavior for multi‑row upserts.
        """
        typed = cast(Dict[str, Any], self.record)
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
        self.last_upserted: Optional[Dict[str, Any]] = None

    def upsert(self, record: Union[Dict[str, Any], List[Dict[str, Any]]]) -> DummyExecutable:
        """
        Accept either a single record or a list of records.

        The real Supabase client accepts both forms, so the dummy client mirrors
        that behavior for test realism.
        """
        if isinstance(record, list):
            self.last_upserted = record[0]
            return DummyExecutable(record[0])
        else:
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
        • upsert(record)
        • list(query)
        • select(...)
        • execute()

    The last two are required by the Protocol but are no‑ops here.
    """

    def __init__(self) -> None:
        self.tables: Dict[str, DummyTableQuery] = {}

    def table(self, name: str) -> DummyTableQuery:
        if name not in self.tables:
            self.tables[name] = DummyTableQuery(name)
        return self.tables[name]

    def upsert(
        self,
        record: Union[Dict[str, Any], List[Dict[str, Any]]],
        on_conflict: Optional[str] = None,
    ) -> SupabaseExecuteResponse:
        """
        Top‑level upsert path.

        Mirrors the Protocol signature and supports both single‑record and
        multi‑record upserts.
        """
        payload = record if isinstance(record, list) else [record]
        return {"status": 200, "data": payload}

    def list(self, query: TableQuery) -> List[NoteRecord]:
        """
        Return a deterministic NoteRecord.

        This ensures predictable behavior in tests without depending on the
        real Supabase backend.
        """
        return [
            {
                "id": "dummy-id",
                "title": "dummy title",
                "body": "dummy body",
                "metadata": {},
                "embedding": [0.0] * 1536,
            }
        ]

    # ------------------------------------------------------------------
    # Required by SupabaseClientInterface but unused in DummyClient
    # ------------------------------------------------------------------

    def select(self, *columns: str) -> Any:
        """
        No‑op select method.

        Real Supabase clients return a query builder, so we return self to
        preserve method‑chaining semantics.
        """
        return self

    def execute(self) -> SupabaseExecuteResponse:
        """
        No‑op execute method.

        Required by the Protocol. Returns an empty successful response.
        """
        return {"status": 200, "data": []}


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

    def upsert(
        self,
        record: Union[Dict[str, Any], List[Dict[str, Any]]],
        on_conflict: Optional[str] = None,
    ) -> SupabaseExecuteResponse:
        return {"status": 500, "data": None}

    def list(self, query: TableQuery) -> List[NoteRecord]:
        raise RuntimeError("Simulated failure")

    # Required by Protocol
    def select(self, *columns: str) -> Any:
        return self

    def execute(self) -> SupabaseExecuteResponse:
        return {"status": 500, "data": None}


# =====================================================================
# FailingTable — Returned by FailingClient.table(name)
# =====================================================================


class FailingTable:
    """
    Returned by FailingClient.table(name).

    Its `.upsert()` returns a FailingExecutable.
    """

    def upsert(self, record: Dict[str, Any]) -> "FailingExecutable":
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
