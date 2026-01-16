# pke/types.py

"""
Typed structures and protocol interfaces used throughout the Personal Knowledge Engine.

This module defines the core data contracts shared between:
    • the ingestion pipeline
    • the embedding generator
    • the CLI
    • the Supabase client (dummy + real)
    • the test suite

These types ensure that all components speak the same language and that
contributors can rely on stable, well‑documented structures when extending
the system.

The goal is to keep the data model explicit, predictable, and easy to mock.
"""

from typing import Any, Dict, List, Protocol, TypedDict


# ---------------------------------------------------------------------------
# NoteRecord — canonical DB representation
# ---------------------------------------------------------------------------


class NoteRecord(TypedDict):
    """
    A single note stored in (or retrieved from) Supabase.

    This is the canonical representation of a note as it exists in the database.
    It is intentionally minimal at this stage of the project.
    """

    id: str
    content: str


# ---------------------------------------------------------------------------
# UpsertNoteRecord — write‑time payload for Supabase
# ---------------------------------------------------------------------------


class UpsertNoteRecord(TypedDict, total=False):
    """
    Payload used when *writing* notes to Supabase.

    This schema intentionally differs from NoteRecord:
        • NoteRecord represents the *database* shape (id, content)
        • UpsertNoteRecord represents the *write‑time* shape (title, body, metadata, embedding)

    The ingestion pipeline constructs this structure before calling:
        client.table("notes").upsert(record).execute()
    """

    id: str
    title: str
    body: str
    metadata: Dict[str, Any]
    embedding: List[float]


# ---------------------------------------------------------------------------
# SupabaseExecuteResponse
# ---------------------------------------------------------------------------


class SupabaseExecuteResponse(TypedDict):
    status: int
    data: Any


# ---------------------------------------------------------------------------
# TableQuery
# ---------------------------------------------------------------------------


class TableQuery(TypedDict):
    table: str
    filters: Dict[str, Any]


# ---------------------------------------------------------------------------
# Executable
# ---------------------------------------------------------------------------


class Executable(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# SupabaseClientInterface
# ---------------------------------------------------------------------------


class SupabaseClientInterface(Protocol):
    """
    Protocol defining the expected behavior of any Supabase client.

    The return type of `.table()` is intentionally Any because:
        • the real Supabase client returns a SyncRequestBuilder
        • DummyClient returns a fake builder
        • the wrapper does not depend on the concrete type
    """

    def table(self, name: str) -> Any: ...

    def upsert(self, notes: List[NoteRecord]) -> SupabaseExecuteResponse: ...

    def list(self, query: TableQuery) -> List[NoteRecord]: ...
