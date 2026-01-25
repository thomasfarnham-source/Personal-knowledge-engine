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
# IngestionSummary
# ---------------------------------------------------------------------------
# Represents the structured summary returned by the ingestion orchestrator.
#
# This TypedDict provides a stable, explicit schema for the ingestion summary
# consumed by:
#   • run_ingest() in the CLI layer
#   • unit tests validating ingestion behavior
#   • higher‑level automation that inspects ingestion results
#
# The orchestrator always returns these fields, making this a reliable
# contract for both human‑readable CLI output and programmatic callers.
# ---------------------------------------------------------------------------


class IngestionSummary(TypedDict):
    notes_processed: int
    notes_inserted: int
    notes_skipped: int
    tags_inserted: int
    relationships_created: int
    failures: List[str]


# ---------------------------------------------------------------------------
# SupabaseExecuteResponse
# ---------------------------------------------------------------------------
# Represents the normalized response returned from Supabase `.execute()`.
#
# The real Supabase client returns a dynamic object with:
#   • .status
#   • .data
#   • .error (optional)
#
# The wrapper (WrappedSupabaseClient) and all test doubles return dictionaries
# with the same fields. This TypedDict captures that shape so mypy can enforce
# correctness across the entire codebase.
#
# total=False allows partial responses (e.g., error-only).
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
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


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
# IMPORTANT:
#   This Protocol is intentionally *structural*, not nominal. Any object that
#   implements these methods with compatible signatures is accepted — including
#   the real Supabase SDK, WrappedSupabaseClient, DummyClient, FakeClient, and
#   FailingClient.
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
        The return value must support .execute().
        """
        ...

    def execute(self) -> SupabaseExecuteResponse:
        """
        Execute the built query and return a structured response.
        """
        ...
