"""
pke/types.py

Centralized type definitions for the Personal Knowledge Engine.

This module defines the core TypedDicts and Protocols used throughout the
ingestion pipeline, Supabase client wrapper, and test stubs. Keeping these
types in one place ensures:

    • A single source of truth for note and metadata schemas
    • Clear contracts between the CLI, ingestion pipeline, and Supabase layer
    • Easy mocking and dependency injection in tests
    • Strong mypy guarantees across the entire project

These types evolve as the data model evolves. When the schema changes in
Supabase or the ingestion pipeline, this file should be updated first.
"""

from typing import Any, Dict, List, Optional, Protocol, TypedDict


# ---------------------------------------------------------------------------
# NoteRecord
# ---------------------------------------------------------------------------
# Represents a single note row stored in Supabase.
#
# This TypedDict mirrors the *actual* schema used by your ingestion pipeline:
#   • title, body, metadata, embedding, notebook_id
#   • id is optional because new notes may not have an ID until Supabase
#     generates one during upsert.
#
# total=False allows partial construction (e.g., before adding "id").
# ---------------------------------------------------------------------------
class NoteRecord(TypedDict, total=False):
    id: str
    title: str
    body: str
    metadata: Dict[str, Any]
    embedding: List[float]
    notebook_id: Optional[str]


# ---------------------------------------------------------------------------
# SupabaseExecuteResponse
# ---------------------------------------------------------------------------
# Represents the response returned from Supabase `.execute()`.
#
# The real Supabase client returns an object with:
#   • .status
#   • .data
#   • .error (optional)
#
# Bucket‑4 hardening:
#   • Added optional "error" field to reflect real Supabase behavior.
#   • This prevents mypy from complaining when client code checks for errors.
# ---------------------------------------------------------------------------
class SupabaseExecuteResponse(TypedDict, total=False):
    status: int
    data: Any
    error: Optional[Any]


# ---------------------------------------------------------------------------
# TableQuery
# ---------------------------------------------------------------------------
# Represents a simple query against a Supabase table.
#
# This is used by test stubs and potential future list/query operations.
# It is intentionally minimal — the ingestion pipeline does not yet require
# complex filtering or pagination.
# ---------------------------------------------------------------------------
class TableQuery(TypedDict):
    table: str
    filters: Dict[str, Any]


# ---------------------------------------------------------------------------
# Executable
# ---------------------------------------------------------------------------
# A generic callable interface.
#
# Used for typing injected functions, callbacks, or command handlers.
# This is intentionally broad — any callable is acceptable.
# ---------------------------------------------------------------------------
class Executable(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        ...


# ---------------------------------------------------------------------------
# SupabaseClientInterface
# ---------------------------------------------------------------------------
# Protocol describing the subset of the Supabase Python client used by
# SupabaseClient (pke/supabase_client.py).
#
# This interface allows:
#   • clean dependency injection
#   • mock clients for tests
#   • mypy to enforce correct method chaining
#
# The real Supabase client supports:
#   client.table("notes").upsert({...}).execute()
#
# Therefore the Protocol must define:
#   • table(name) -> Any
#   • upsert(record, on_conflict?) -> Any
#   • select(...) -> Any
#   • execute() -> SupabaseExecuteResponse
#
# Bucket‑4 hardening:
#   • Added explicit return type for execute()
#   • Ensured upsert() and select() signatures match real usage
#   • This keeps mocks and stubs aligned with the hardened client wrapper
# ---------------------------------------------------------------------------
class SupabaseClientInterface(Protocol):
    def table(self, name: str) -> Any:
        """
        Return a query builder for the given table.
        The returned object must support .upsert(), .select(), and .execute().
        """
        ...

    def upsert(
        self,
        record: Dict[str, Any],
        on_conflict: Optional[str] = None,
    ) -> Any:
        """
        Insert or update a row in the table.
        The return value is a query builder that must support .execute().
        """
        ...

    def select(self, *columns: str) -> Any:
        """
        Select specific columns from the table.
        The return value is a query builder that must support .execute().
        """
        ...

    def execute(self) -> SupabaseExecuteResponse:
        """
        Execute the built query and return a structured response.
        """
        ...