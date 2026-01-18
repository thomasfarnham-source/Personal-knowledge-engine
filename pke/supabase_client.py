# pke/supabase_client.py = Part 1 =

"""
Minimal Supabase client wrapper for local testing and upserting notes with embeddings.

This module centralizes all Supabase interactions behind a small, typed wrapper so that:
- ingestion code does not depend directly on the Supabase SDK
- tests can swap in dummy or fake clients
- entity resolution (e.g., notebooks) is explicit and predictable
- embedding computation is handled in one place

Key responsibilities:
- Construct a Supabase client from environment variables (via from_env()).
- Normalize Supabase responses into plain Python data structures.
- Provide helpers for:
    • resolving notebook IDs by title (resolve_notebook_id)
    • upserting notes with embeddings (upsert_note_with_embedding)
"""
from typing import cast

import os
from typing import Any, Dict, List, Optional

from supabase import Client, create_client  # Third-party SDK
from pke.embedding import compute_embedding  # Local embedding stub
from pke.types import (
    NoteRecord,  # ✅ Re-exported for tests
    UpsertNoteRecord,  # ✅ Correct write-time payload type
    Executable,
    SupabaseExecuteResponse,
    TableQuery,
)
from pke.wrapped_supabase_client import WrappedSupabaseClient  # ✅ Used in production

# ✅ IMPORTANT DESIGN DECISION
# We intentionally do NOT type the injected client as SupabaseClientInterface.
# The real Supabase SDK client does NOT implement our Protocol (it lacks .list, .upsert),
# and mypy will reject it. Instead, we accept Any and rely on duck typing.
#
# The Protocol still exists in pke.types for tests, stubs, and future real-client wrappers.


# ---------------------------------------------------------------------------
# Helper: normalize Supabase responses
# ---------------------------------------------------------------------------


def _extract_data(resp: Any) -> List[UpsertNoteRecord]:
    """
    Normalize Supabase responses across:
        • real SDK objects
        • DummyClient-style dicts
        • test stubs

    Always returns a list of row dictionaries.

    Raises RuntimeError on any Supabase error.
    """
    # Case 1: DummyClient-style dict
    if isinstance(resp, dict):
        if resp.get("status", 200) >= 400:
            raise RuntimeError(f"Supabase error: {resp}")
        return cast(List[UpsertNoteRecord], resp.get("data", []))

    # Case 2: Real Supabase SDK object (or wrapped equivalent)
    if getattr(resp, "error", None):
        raise RuntimeError(f"Supabase error: {resp.error}")

    return cast(List[UpsertNoteRecord], getattr(resp, "data", None) or [])


# ---------------------------------------------------------------------------
# Main wrapper class
# ---------------------------------------------------------------------------


class SupabaseClient:
    """
    A minimal, dependency-injected wrapper around a Supabase-like client.

    This class is intentionally small and focused:
    - It does not know about environment variables directly (except via from_env()).
    - It delegates low-level operations to an underlying client (real or dummy).
    - It exposes higher-level helpers for ingestion and entity resolution.

    Notes
    -----
    We intentionally accept Any for the injected client because the real Supabase
    SDK does not satisfy our Protocol. This keeps the wrapper flexible and mypy-clean
    while still allowing DummyClient and test stubs to conform to the Protocol.
    """

    def __init__(self, client: Any) -> None:
        """
        Initialize the wrapper with a concrete client.

        The client is expected to behave like WrappedSupabaseClient:
        - .table(name) -> TableQuery-like object
        - query builders support .select(), .eq(), .insert(), .upsert(), .execute()

        This design allows:
            • dependency injection
            • easy mocking in tests
            • swapping between DummyClient and real Supabase client
            • clean separation between business logic and network logic
        """
        self.client = client

    @classmethod
    def from_env(cls) -> "SupabaseClient":
        """
        Factory constructor that initializes SupabaseClient using environment variables.

        This is the canonical way to construct a SupabaseClient in application code.

        Expected environment variables:
        - SUPABASE_URL
        - SUPABASE_SERVICE_ROLE_KEY

        Raises
        ------
        RuntimeError
            If either environment variable is missing.
        """
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not key:
            raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment.")

        # Create the real Supabase client via the official SDK.
        real_client: Client = create_client(url, key)

        # Wrap it in our adapter to normalize behavior and typing.
        wrapped = WrappedSupabaseClient(real_client)

        # Inject the wrapped client into our abstraction.
        return cls(client=wrapped)

    def table(self, name: str) -> TableQuery:
        """
        Return a table query object for the given table name.

        This is a thin pass-through to the underlying client, but typed
        to make mypy and contributors happier.

        Notes
        -----
        The return type is intentionally Any because:
            • the real Supabase client returns a SyncRequestBuilder
            • DummyClient returns a fake builder
            • the wrapper does not depend on the concrete type

        Raises
        ------
        RuntimeError
            If no client has been injected.
        """
        if not self.client:
            raise RuntimeError("Supabase client is not configured")

        return self.client.table(name)

    # -----------------------------------------------------------------------
    # Notebook resolution ==== Part 2 ====
    # -----------------------------------------------------------------------

    def resolve_notebook_id(self, notebook_title: Optional[str]) -> Optional[str]:
        """
        Resolve the UUID of a notebook by title.

        Steps:
            1. If no title provided → return None (caller decides how to handle).
            2. SELECT id FROM notebooks WHERE title = <title>.
            3. If exists → return id.
            4. If not → INSERT {title} and return new id.

        This method is intentionally conservative:
            • No assumptions about schema beyond "id" and "title".
            • No caching (yet) — correctness > performance.
            • Fully normalized error handling via _extract_data().

        Parameters
        ----------
        notebook_title : str | None
            The human-readable notebook title extracted from parsed notes.

        Returns
        -------
        str | None
            The resolved notebook UUID, or None if no title was provided.
        """
        if not notebook_title:
            # Notes without notebooks are allowed; caller handles fallback.
            return None

        if not self.client:
            raise RuntimeError("Supabase client is not configured")

        # 1. Lookup existing notebook
        select_resp: SupabaseExecuteResponse = (
            self.client.table("notebooks").select("id").eq("title", notebook_title).execute()
        )

        rows = _extract_data(select_resp)
        if rows:
            # Notebook already exists — return its UUID.
            return rows[0]["id"]

        # 2. Insert new notebook
        insert_payload: Dict[str, Any] = {"title": notebook_title}

        insert_resp: SupabaseExecuteResponse = (
            self.client.table("notebooks").insert(insert_payload).execute()
        )

        inserted = _extract_data(insert_resp)
        if not inserted:
            raise RuntimeError(f"Notebook insert returned no rows for title={notebook_title!r}")

        return inserted[0]["id"]

    # -----------------------------------------------------------------------
    # Note upsert with embedding
    # -----------------------------------------------------------------------

    def upsert_note_with_embedding(
        self,
        title: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
        id: Optional[str] = None,
        notebook_id: Optional[str] = None,
        table: str = "notes",
    ) -> List[UpsertNoteRecord]:
        """
        Upsert a note into the given table, computing an embedding for the body.

        Parameters
        ----------
        title : str
            Human-readable note title.
        body : str
            Note body content. Must be non-empty.
        metadata : dict | None
            Arbitrary metadata to store alongside the note.
        id : str | None
            Optional explicit note ID for deterministic upserts.
        notebook_id : str | None
            Optional foreign key to the notebooks table.
        table : str
            Target table name. Defaults to "notes".

        Returns
        -------
        list[UpsertNoteRecord]
            The rows returned by Supabase after the upsert, each conforming to
            the UpsertNoteRecord TypedDict.


        Raises
        ------
        ValueError
            If body is empty.
        RuntimeError
            If the underlying client is not configured or Supabase returns an error.
        """
        if not body:
            raise ValueError("body must be provided")

        if not self.client:
            raise RuntimeError(
                "No client provided to SupabaseClient. "
                "Please construct via SupabaseClient.from_env() or inject a valid client."
            )

        # Compute embedding for the note body.
        emb = compute_embedding(body)

        from typing import cast
        from pke.types import UpsertNoteRecord

        record: UpsertNoteRecord = cast(
            UpsertNoteRecord,
            {
                "title": title,
                "body": body,
                "metadata": metadata or {},
                "embedding": emb,
            },
        )

        if id:
            record["id"] = id
        if notebook_id:
            record["notebook_id"] = notebook_id

        resp: SupabaseExecuteResponse = self.client.table(table).upsert(record).execute()

        # Normalize error handling.
        if isinstance(resp, dict) and resp.get("status", 200) >= 400:
            raise RuntimeError(f"Upsert error: {resp}")
        if not isinstance(resp, dict) and getattr(resp, "error", None):
            raise RuntimeError(f"Upsert error: {resp.error}")

        data = _extract_data(resp)
        return data


__all__ = [
    "SupabaseClient",
    "Executable",
    "SupabaseExecuteResponse",
    "TableQuery",
    "NoteRecord",  # ✅ required for tests
    "UpsertNoteRecord",  # ✅ optional but helpful
]
