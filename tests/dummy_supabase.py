"""
DummyClient for local testing of SupabaseClient.

This module defines a fully typed, in-memory mock of the Supabase client chain:
    client.table(name).upsert(record).execute()

It is used in conjunction with `supabase_client.py` to test the behavior of
SupabaseClient without making real network calls. It supports deterministic
testing of upsert logic, embedding flow, and error handling.

Place this file in:
    tests/dummy_supabase.py

Usage in tests:
    from supabase_client import SupabaseClient
    from tests.dummy_supabase import DummyClient

    client = SupabaseClient(client=DummyClient())
    result = client.upsert_note_with_embedding(title="Test", body="Hello world!")
"""

from typing import Any, Dict, List, Optional
from supabase_client import (
    SupabaseClientInterface,
    TableQuery,
    Executable,
    NoteRecord,
    SupabaseExecuteResponse,
)


class DummyExecuteResponse:
    """
    Simulates the response object returned by Supabase .execute().

    Attributes:
        data: The simulated response payload (typically a list of records).
        error: Optional error message to simulate failure cases.
    """

    def __init__(self, data: Any = None, error: Optional[str] = None):
        self.data = data
        self.error = error


class DummyExecutable(Executable):
    """
    Simulates the final .execute() call in the Supabase chain.

    This class is returned by DummyTableQuery.upsert() and holds the record
    to be "upserted". When .execute() is called, it returns a DummyExecuteResponse.
    """

    def __init__(self, record: NoteRecord):
        self.record = record

    def execute(self) -> SupabaseExecuteResponse:
        # Simulate a successful upsert by returning the record in a list
        return DummyExecuteResponse(data=[self.record])


class DummyTableQuery(TableQuery):
    """
    Simulates the .upsert() call on a Supabase table.

    This class is returned by DummyClient.table(name) and stores the last
    upserted record for inspection in tests.
    """

    def __init__(self, table_name: str):
        self.table_name = table_name
        self.last_upserted: Optional[NoteRecord] = None

    def upsert(self, record: NoteRecord) -> Executable:
        self.last_upserted = record  # Store for test assertions
        return DummyExecutable(record)


class DummyClient(SupabaseClientInterface):
    """
    Simulates the Supabase client for local testing.

    Implements the full method chain:
        .table(name) → .upsert(record) → .execute()

    This class is injected into SupabaseClient during tests to avoid real
    network calls and enable deterministic behavior.
    """

    def __init__(self):
        # Store table-specific mocks for inspection or reuse
        self.tables: Dict[str, DummyTableQuery] = {}

    def table(self, name: str) -> TableQuery:
        # Return a reusable DummyTableQuery for the given table name
        if name not in self.tables:
            self.tables[name] = DummyTableQuery(name)
        return self.tables[name]
