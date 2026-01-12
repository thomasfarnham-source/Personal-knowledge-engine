"""
Minimal Supabase client wrapper for local testing and upserting notes with embeddings.

This module provides a thin, typed wrapper around an injected Supabase-like client.
It ensures:
    - deterministic behavior in tests,
    - strict mypy compliance,
    - a stable interface for contributors,
    - and a single place where embedding + upsert logic is coordinated.

The wrapper does NOT depend on the real Supabase SDK directly. Instead, it expects
an injected client that implements SupabaseClientInterface, allowing both the real
WrappedSupabaseClient and DummyClient to be used interchangeably.
"""

from pke.wrapped_supabase_client import WrappedSupabaseClient

import os
from typing import Any, Dict, Optional

from supabase import Client, create_client  # Third-party SDK
from pke.embedding import compute_embedding  # Local embedding function
from pke.types import (  # Local typed interfaces
    NoteRecord,
    SupabaseClientInterface,
    Executable,
    SupabaseExecuteResponse,
    TableQuery,
)


class SupabaseClient:
    """
    A minimal, dependency-injected wrapper around a Supabase-like client.

    This class does not know or care whether the underlying client is:
        - the real Supabase Python SDK (wrapped),
        - a dummy in-memory client for tests,
        - or any other implementation.

    All that matters is that the injected client implements SupabaseClientInterface.
    """

    def __init__(self, client: Optional[SupabaseClientInterface] = None):
        """
        Store the injected client.

        Args:
            client:
                An object implementing SupabaseClientInterface. This allows the
                wrapper to remain fully testable and mypy-compliant.
        """
        self.client = client

    def table(self, name: str) -> Any:
        """
        Proxy access to the underlying client's `.table(name)` method.

        This is rarely used directly, but is provided for completeness and
        parity with the real Supabase client.

        Raises:
            RuntimeError: If no client has been injected.
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
        Compute an embedding for the note body and upsert the resulting record
        into the specified Supabase table.

        This method centralizes:
            - embedding computation,
            - NoteRecord construction,
            - and the upsert call.

        Args:
            title:
                Human-readable title for the note.
            body:
                The main text content. Required for embedding.
            metadata:
                Optional metadata dictionary. Defaults to {}.
            id:
                Optional note ID. If provided, ensures deterministic upsert behavior.
            table:
                Supabase table name. Defaults to "notes".

        Returns:
            The `.data` field from the SupabaseExecuteResponse.

        Raises:
            ValueError:
                If `body` is empty.
            RuntimeError:
                If no client is configured or if the Supabase response indicates an error.
        """
        if not body:
            raise ValueError("body must be provided")

        if not self.client:
            raise RuntimeError(
                "No client provided to SupabaseClient. "
                "Please pass a valid client instance or use the default."
            )

        # Compute the embedding vector for the note body.
        emb = compute_embedding(body)

        # Construct a fully populated NoteRecord.
        # All fields are required by the TypedDict definition.
        record: NoteRecord = {
            "id": id or "",              # Use provided ID or fallback to empty string
            "content": body,             # Full raw text content for search/display
            "title": title,              # Human-readable title
            "body": body,                # Cleaned or formatted body content
            "metadata": metadata or {},  # Optional metadata
            "embedding": emb,            # 1536-dimensional embedding vector
        }

        # Perform the upsert via the injected client.
        # The wrapped real client returns a dict; DummyClient returns a dict as well.
        resp = self.client.table(table).upsert(record).execute()

        # Handle wrapped-client error format: {"status": int, "data": ..., "error": ...}
        if isinstance(resp, dict) and resp.get("status", 200) >= 400:
            raise RuntimeError(f"Upsert error: {resp}")

        # Handle DummyClient-style object responses (with .data)
        if not isinstance(resp, dict) and getattr(resp, "error", None):
            raise RuntimeError(f"Upsert error: {resp.error}")

        # Normalize return value: always return the data payload.
        return resp["data"] if isinstance(resp, dict) else resp.data


# === Shared instance for application use ===

# Load Supabase credentials from environment variables.
# Defaults allow local development without requiring real credentials.
SUPABASE_URL = os.getenv("SUPABASE_URL", "http://localhost:54321")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "test-key")

# Create the raw Supabase client using the official SDK.
real_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Wrap the raw client in a type-safe adapter that conforms to SupabaseClientInterface.
# This ensures mypy validation and consistent behavior across environments.
supabase: SupabaseClient = SupabaseClient(WrappedSupabaseClient(real_client))

# Explicit exports for clarity and tooling.
__all__ = [
    "SupabaseClient",
    "supabase",
    "Executable",
    "SupabaseExecuteResponse",
    "TableQuery",
]
