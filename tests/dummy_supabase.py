"""
DummyClient and FailingClient for local testing of SupabaseClient.

These classes simulate the Supabase client method chain:

    client.table(name).upsert(record).execute()

They allow the ingestion pipeline and SupabaseClient wrapper to be tested
without making real network calls. The goal is deterministic, fully typed,
in‑memory behavior that mirrors the real client’s shape closely enough for
unit tests.
"""

from typing import Any, Dict, Optional

from pke.types import (
    UpsertNoteRecord,
    SupabaseExecuteResponse,
)
from pke.supabase_client import Executable


# ---------------------------------------------------------------------------
# DummyExecuteResponse — simple stand‑in for SupabaseExecuteResponse
# ---------------------------------------------------------------------------


class DummyExecuteResponse:
    """
    Minimal stand‑in for the response object returned by Supabase `.execute()`.

    This mirrors the shape of SupabaseExecuteResponse:
        • data: payload returned by the operation
        • error: optional error message
    """

    def __init__(self, data: Any = None, error: Optional[str] = None) -> None:
        self.data = data
        self.error = error


# ---------------------------------------------------------------------------
# DummyExecutable — returned by DummyTableQuery.upsert()
# ---------------------------------------------------------------------------


class DummyExecutable(Executable):
    """
    Represents the final `.execute()` call in the Supabase chain.

    DummyTableQuery.upsert() returns an instance of this class. When `.execute()`
    is called, it returns a DummyExecuteResponse containing the upserted record.
    """

    def __init__(self, record: UpsertNoteRecord) -> None:
        self.record = record

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """
        Required to satisfy the Executable Protocol.
        The real Supabase request builder is callable; our dummy simply no‑ops.
        """
        return None

    def execute(self) -> SupabaseExecuteResponse:
        """
        Execute the request and return a SupabaseExecuteResponse‑compatible object.

        Notes
        -----
        SupabaseExecuteResponse is a strict TypedDict with only:
            • status : int
            • data   : Any

        The real Supabase Python client attaches errors as *attributes* on the
        response object (e.g., response.error), not as dictionary keys.

        To accurately simulate that behavior while keeping mypy satisfied, we:
            1. Construct a valid SupabaseExecuteResponse dictionary.
            2. Dynamically attach an `.error` attribute to the dict instance.
               This is allowed because TypedDicts can carry extra attributes,
               just not extra *keys*.

        This preserves type safety while matching real‑world behavior.
        """
        # Step 1: Construct a valid SupabaseExecuteResponse dictionary.
        resp: SupabaseExecuteResponse = {"status": 200, "data": [self.record]}

        # Step 2: Attach an error attribute dynamically (none for success).
        setattr(resp, "error", None)

        return resp


# ---------------------------------------------------------------------------
# DummyTableQuery — returned by DummyClient.table()
# ---------------------------------------------------------------------------


class DummyTableQuery:
    """
    Simulates the `.upsert()` call on a Supabase table.

    Stores the last upserted record so tests can assert on it.
    """

    def __init__(self, table_name: str) -> None:
        self.table_name = table_name
        self.last_upserted: Optional[UpsertNoteRecord] = None

    def upsert(self, record: UpsertNoteRecord) -> DummyExecutable:
        """
        Store the record and return a DummyExecutable that will produce
        a deterministic response when `.execute()` is called.
        """
        self.last_upserted = record
        return DummyExecutable(record)


# ---------------------------------------------------------------------------
# DummyClient — successful Supabase‑like client
# ---------------------------------------------------------------------------


class DummyClient:
    """
    Simulates a Supabase client that always succeeds.

    Implements the method chain:
        .table(name) → DummyTableQuery → DummyExecutable → DummyExecuteResponse
    """

    def __init__(self) -> None:
        self.tables: Dict[str, DummyTableQuery] = {}

    def table(self, name: str) -> DummyTableQuery:
        """
        Return a DummyTableQuery for the given table name.
        """
        if name not in self.tables:
            self.tables[name] = DummyTableQuery(name)
        return self.tables[name]


# ---------------------------------------------------------------------------
# FailingClient — always returns an error on execute()
# ---------------------------------------------------------------------------


class FailingClient:
    """
    A test double that simulates a Supabase client returning an error.

    Useful for verifying that SupabaseClient correctly propagates errors.
    """

    class FailingExecutable(Executable):
        def __call__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def execute(self) -> SupabaseExecuteResponse:
            """
            Always return an error response.

            This mirrors the real Supabase client, which attaches `.error`
            as an attribute rather than including it in the dictionary keys.
            """
            # Construct a valid SupabaseExecuteResponse dictionary.
            resp: SupabaseExecuteResponse = {"status": 500, "data": None}

            # Attach the error attribute dynamically.
            setattr(resp, "error", "Simulated failure")

            return resp

    class FailingTable:
        """
        Minimal table object that returns a failing executable.
        """

        def upsert(self, record: UpsertNoteRecord) -> "FailingClient.FailingExecutable":
            return FailingClient.FailingExecutable()

    def table(self, name: str) -> "FailingClient.FailingTable":
        """
        Return a table object whose `.upsert()` always fails.
        """
        return FailingClient.FailingTable()
