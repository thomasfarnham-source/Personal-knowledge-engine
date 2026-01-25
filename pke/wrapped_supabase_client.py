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

from typing import Any, Dict, List, Optional, Union
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

    def upsert(
        self,
        record: Union[Dict[str, Any], List[Dict[str, Any]]],
        on_conflict: Optional[str] = None,
    ) -> SupabaseExecuteResponse:
        """
        Perform an upsert into the "notes" table.

        This method intentionally matches the SupabaseClientInterface signature:

            def upsert(self, record: Dict[str, Any], on_conflict: Optional[str]) -> Any

        but is extended to also accept a list of records. This keeps the method
        Protocol‑compatible (it still accepts a single Dict[str, Any]) while allowing
        callers to batch‑upsert multiple rows.

        The underlying Supabase Python client accepts either a single dictionary or
        a list of dictionaries for upsert operations. To keep behavior predictable
        and mypy‑friendly, we normalize both cases into a list before calling the SDK.

        Args:
            record:
                Either a single NoteRecord dictionary or a list of NoteRecord
                dictionaries. Both forms are normalized into a list internally.
            on_conflict:
                Optional column name used by Supabase to determine the conflict
                target for the upsert. Passed directly to the underlying SDK.

        Returns:
            A SupabaseExecuteResponse TypedDict containing normalized "status" and
            "data" fields extracted from the underlying SDK response. The Supabase
            client exposes dynamic attributes (e.g., .status, .status_code, .data),
            so we treat the response as Any and read attributes defensively.
        """

        # Normalize input to a list so the SDK always receives a consistent payload.
        if isinstance(record, list):
            payload = record
        else:
            payload = [record]

        # Perform the upsert. The Supabase SDK is dynamically typed, so we silence
        # the arg-type warning when passing our JSON-serializable payload.
        response = (
            self._client.table("notes")
            .upsert(payload, on_conflict=on_conflict)  # type: ignore[arg-type]
            .execute()
        )

        # Treat the SDK response as dynamic to avoid mypy attribute errors.
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
