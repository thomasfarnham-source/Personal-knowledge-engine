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
    It includes both raw content and structured fields used for semantic search.

    Fields
    ------
    id : str
        Unique identifier for the note (e.g., UUID or source-derived ID).
    content : str
        Raw or normalized text content of the note.
    title : str
        Human-readable title (e.g., from Evernote or email subject).
    body : str
        Cleaned or formatted body content (e.g., markdown or plain text).
    metadata : Dict[str, str]
        Arbitrary metadata such as source, tags, timestamps, or author.
    embedding : List[float]
        1536-dimensional vector used for semantic search and similarity.
    """

    id: str
    content: str
    title: str
    body: str
    metadata: Dict[str, str]
    embedding: List[float]


# ---------------------------------------------------------------------------
# UpsertNoteRecord — write‑time payload for Supabase
# ---------------------------------------------------------------------------


class UpsertNoteRecord(TypedDict, total=False):
    """
    Payload used when *writing* notes to Supabase.

    This schema intentionally differs from NoteRecord:
        • NoteRecord represents the *database* shape (fully populated)
        • UpsertNoteRecord represents the *write‑time* shape (partial, optional)

    The ingestion pipeline constructs this structure before calling:
        client.table("notes").upsert(record).execute()
    """

    id: str
    title: str
    body: str
    metadata: Dict[str, Any]
    embedding: List[float]


# ---------------------------------------------------------------------------
# SupabaseExecuteResponse — result of a write operation
# ---------------------------------------------------------------------------


class SupabaseExecuteResponse(TypedDict):
    """
    Standardized response structure for Supabase write operations.

    This mirrors the shape of responses returned by the Supabase Python client,
    but is simplified for local testing and type‑checking.

    Fields
    ------
    status : int
        HTTP-like status code (e.g., 200 for success).
    data : Any
        Optional payload returned by the operation (e.g., inserted rows).
    """

    status: int
    data: Any


# ---------------------------------------------------------------------------
# TableQuery — structured query for SupabaseClient.list()
# ---------------------------------------------------------------------------


class TableQuery(TypedDict):
    """
    Represents a structured query against a Supabase table.

    This type is used by the Supabase client interface to support list/retrieval
    operations. It keeps the query shape explicit and testable.

    Fields
    ------
    table : str
        Name of the table to query (e.g., "notes").
    filters : Dict[str, Any]
        Key‑value filters to apply (e.g., {"id": "abc123"}).
    """

    table: str
    filters: Dict[str, Any]


# ---------------------------------------------------------------------------
# Executable — generic callable interface
# ---------------------------------------------------------------------------


class Executable(Protocol):
    """
    Generic callable interface used for type‑checking injected functions.

    This is useful when:
        • wiring CLI commands to handler functions
        • injecting mock behaviors during tests
        • building modular pipelines with pluggable steps

    Any function matching this signature can be treated as an Executable.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# SupabaseClientInterface — protocol for injected Supabase clients
# ---------------------------------------------------------------------------


class SupabaseClientInterface(Protocol):
    """
    Protocol defining the expected behavior of any Supabase client.

    This abstraction allows the system to swap between:
        • DummyClient (local testing, no network)
        • Real Supabase client (production)
        • Test stubs (unit tests)

    Notes
    -----
    The return type of `.table()` is intentionally `Any` because:
        • the real Supabase client returns a SyncRequestBuilder
        • DummyClient returns a fake builder
        • the wrapper does not depend on the concrete type
    """

    def table(self, name: str) -> Any: ...
    def upsert(self, notes: List[NoteRecord]) -> SupabaseExecuteResponse: ...
    def list(self, query: TableQuery) -> List[NoteRecord]: ...
