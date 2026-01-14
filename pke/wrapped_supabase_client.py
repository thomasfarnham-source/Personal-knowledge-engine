"""
WrappedSupabaseClient

This adapter wraps the official Supabase Python client and exposes a stable,
typed interface that matches SupabaseClientInterface. It provides:

    - .table(name)
    - .upsert(notes)
    - .list(query)

The real Supabase client is highly dynamic and not statically typed, so this
wrapper normalizes responses into predictable Python dictionaries that match
SupabaseExecuteResponse.

This ensures:
    - strict mypy compliance,
    - clean separation between your app and the external SDK,
    - and consistent behavior across production and tests.
"""

from typing import Any, List
from supabase import Client

from pke.types import (
    SupabaseClientInterface,
    NoteRecord,
    SupabaseExecuteResponse,
    TableQuery,
)


class WrappedSupabaseClient(SupabaseClientInterface):
    """
    Adapter around the official Supabase Python client.

    The real client exposes a dynamic query builder (e.g., .table().eq().select()),
    which mypy cannot type-check. This wrapper adds the minimal structure needed
    to satisfy SupabaseClientInterface and normalize responses.
    """

    def __init__(self, client: Client):
        """
        Store the raw Supabase client instance.

        Args:
            client:
                The official Supabase Python client created via create_client().
        """
        self._client = client

    def table(self, name: str) -> Any:
        """
        Return a chainable query builder for the given table.

        Supabase's query builder is dynamic and untyped, so we return Any.
        """
        return self._client.table(name)

    def upsert(self, notes: List[NoteRecord]) -> SupabaseExecuteResponse:
        """
        Perform an upsert into the "notes" table.

        The Supabase Python client expects JSON-serializable data, but mypy
        cannot verify that NoteRecord is JSON-compatible. We silence the false
        positive with a targeted type ignore when calling the SDK.

        We also normalize the SDK response into the SupabaseExecuteResponse
        TypedDict. The SDK's response object shape can vary; to avoid mypy
        attribute errors we treat the SDK response as Any and read attributes
        dynamically.
        """
        response = self._client.table("notes").upsert(notes).execute()  # type: ignore[arg-type]

        # Treat the SDK response as dynamic to avoid attribute errors from mypy.
        response_any: Any = response

        # Normalize status: some SDK versions expose `status`, others `status_code`.
        status = getattr(response_any, "status", getattr(response_any, "status_code", 200))

        # Normalize data payload; SDK typically exposes `.data`.
        data = getattr(response_any, "data", None)

        return {
            "status": status,
            "data": data,
        }

    def list(self, query: TableQuery) -> List[NoteRecord]:
        """
        Execute a filtered SELECT query.

        TableQuery is a TypedDict with:
            - "table": str
            - "filters": Dict[str, Any]

        Supabase's query builder exposes dynamic filter methods like `.eq()`,
        which mypy cannot see. We silence the attribute error on `.eq()`.

        Returns:
            A list of NoteRecord dictionaries.
        """
        table = self._client.table(query["table"])

        # Apply each filter dynamically
        for key, value in query["filters"].items():
            table = table.eq(key, value)  # type: ignore[attr-defined]

        # Execute the SELECT query
        response = table.select("*").execute()

        # The Supabase client returns untyped JSON data; treat as Any and return .data
        response_any: Any = response
        return response_any.data
