# pke/types.py

from typing import Any, Dict, List, Protocol, TypedDict


# Represents a single note stored in Supabase, including its content, metadata, and embedding.
# This structure is used for both inserting and retrieving notes from the database.
class NoteRecord(TypedDict):
    id: str  # Unique identifier for the note (UUID or similar)
    content: str  # Full raw text content of the note (used for search/display)
    title: str  # Human-readable title of the note (e.g., from Evernote or email subject)
    body: str  # Cleaned or formatted body content (e.g., HTML-stripped or markdown)
    metadata: Dict[str, str]  # Arbitrary metadata (e.g., source, tags, timestamps, author)
    embedding: List[float]  # 1536-dimensional vector representation for semantic search


# Represents the response returned from a Supabase operation (e.g., upsert).
# Includes status code and optional data payload.
class SupabaseExecuteResponse(TypedDict):
    status: int  # HTTP-like status code (e.g., 200 for success)
    data: Any  # Optional response data (e.g., inserted rows)


# Represents a query against a Supabase table.
# Used to filter and retrieve notes based on table name and filter criteria.
class TableQuery(TypedDict):
    table: str  # Name of the Supabase table (e.g., "notes")
    filters: Dict[str, Any]  # Key-value filters to apply (e.g., {"user_id": "abc123"})


# A generic callable interface for any executable function.
# Used to type-check injected functions or command handlers.
class Executable(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


# Defines the expected interface for a Supabase client implementation.
# This allows you to swap in mocks or stubs for testing.
class SupabaseClientInterface(Protocol):
    def table(self, name: str) -> Any: ...
    def upsert(self, notes: List[NoteRecord]) -> SupabaseExecuteResponse: ...
    def list(self, query: TableQuery) -> List[NoteRecord]: ...
