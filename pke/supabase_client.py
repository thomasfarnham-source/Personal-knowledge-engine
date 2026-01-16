# pke/supabase_client.py

"""
Minimal Supabase client wrapper for local testing and upserting notes with embeddings.

This module provides a thin abstraction layer around a Supabase-like client.
It is intentionally minimal at this stage of the project and serves two goals:

    1. Allow the ingestion pipeline to upsert notes with embeddings.
    2. Provide a stable interface for swapping in:
         • DummyClient (local testing)
         • Real Supabase client (production)
         • Test stubs (unit tests)

As the project matures, this wrapper will evolve into the production-ready
client under the target-state structure (pke/supabase/real_client.py).
"""

import os
from typing import Any, Dict, Optional

from supabase import Client, create_client  # Third‑party SDK
from pke.embedding import compute_embedding  # Local embedding stub
from pke.types import (
    NoteRecord,  # ✅ re-exported for tests
    UpsertNoteRecord,  # ✅ correct write‑time payload type
    Executable,
    SupabaseExecuteResponse,
    TableQuery,
)

# ✅ IMPORTANT DESIGN DECISION
# We intentionally do NOT type the injected client as SupabaseClientInterface.
# The real Supabase SDK client does NOT implement our Protocol (it lacks .list, .upsert),
# and mypy will reject it. Instead, we accept Any and rely on duck typing.
#
# The Protocol still exists in pke.types for tests, stubs, and future real-client wrappers.


class SupabaseClient:
    """
    A minimal wrapper around an injected Supabase-like client.

    This class does not directly communicate with Supabase. Instead, it expects
    an injected client that implements the method chain:

        .table(name).upsert(record).execute()

    This design allows:
        • dependency injection
        • easy mocking in tests
        • swapping between DummyClient and real Supabase client
        • clean separation between business logic and network logic
    """

    def __init__(self, client: Any = None) -> None:
        """
        Initialize the SupabaseClient with an optional injected client.

        Parameters
        ----------
        client : Any
            Any object that implements the Supabase-like method chain.
            This may be:
                • a real Supabase client (via supabase-py)
                • a DummyClient for local testing
                • a test stub for unit tests

        Notes
        -----
        We intentionally accept Any here because the real Supabase SDK does not
        satisfy our Protocol. This keeps the wrapper flexible and mypy-clean.
        """
        self.client = client

    def table(self, name: str) -> Any:
        """
        Proxy access to the underlying client's .table(name) method.

        The return type is intentionally Any because:
            • the real Supabase client returns a SyncRequestBuilder
            • DummyClient returns a fake builder
            • the wrapper does not depend on the concrete type
        """
        if not self.client:
            raise RuntimeError("Supabase client is not configured")
        return self.client.table(name)

    def upsert_note_with_embedding(
        self,
        title: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
        id: Optional[str] = None,
        table: str = "notes",
    ) -> Any:
        """
        Compute an embedding for the note body and upsert the note.

        The payload shape used here is UpsertNoteRecord, which represents
        the write-time schema (title, body, metadata, embedding, id).
        This is intentionally different from NoteRecord, which represents
        the database schema (id, content).
        """
        if not body:
            raise ValueError("body must be provided")

        if not self.client:
            raise RuntimeError(
                "No client provided to SupabaseClient. "
                "Please pass a valid client instance or use the default."
            )

        # Compute deterministic embedding using the local stub.
        emb = compute_embedding(body)

        # ✅ Correct payload type: UpsertNoteRecord, not NoteRecord.
        record: UpsertNoteRecord = {
            "title": title,
            "body": body,
            "metadata": metadata or {},
            "embedding": emb,
        }

        if id:
            record["id"] = id

        # Perform the upsert operation.
        resp = self.client.table(table).upsert(record).execute()

        # Normalize error handling.
        if getattr(resp, "error", None):
            raise RuntimeError(f"Upsert error: {resp.error}")

        return resp.data


# ---------------------------------------------------------------------------
# Shared instance for application use
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL", "http://localhost:54321")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "test-key")

# Create the real Supabase client using the official SDK.
real_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Wrap the real client in our abstraction layer.
supabase: SupabaseClient = SupabaseClient(real_client)

# ✅ Re-export types that tests expect to import from this module.
__all__ = [
    "SupabaseClient",
    "supabase",
    "Executable",
    "SupabaseExecuteResponse",
    "TableQuery",
    "NoteRecord",  # ✅ required for tests
    "UpsertNoteRecord",  # ✅ optional but helpful
]
