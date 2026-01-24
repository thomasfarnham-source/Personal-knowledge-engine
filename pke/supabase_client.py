# ------------------------------------------------------------
# SECTION 1 — Updated for ease of review
# ------------------------------------------------------------
"""
Minimal Supabase client wrapper for local testing and upserting notes with embeddings.

This wrapper provides a stable, typed interface for interacting with Supabase
during ingestion. It supports both real mode (using the Supabase Python client)
and dry‑run mode (deterministic, no‑write behavior for testing and debugging).

The class relies on the SupabaseClientInterface Protocol defined in pke/types.py,
which ensures that injected clients (real or mock) expose the minimal surface:
    • table(name)
    • upsert(record, on_conflict?)
    • select(...)
    • execute()
"""

import os
from typing import Any, Dict, Optional

from supabase import Client, create_client  # Third‑party SDK
from pke.embedding import compute_embedding  # Local embedding helper
from pke.types import (
    NoteRecord,
    SupabaseClientInterface,
    Executable,
    SupabaseExecuteResponse,
    TableQuery,
)


class SupabaseClient:
    """
    A minimal wrapper around a Supabase‑compatible client.

    This class is intentionally thin: it forwards calls to the underlying
    Supabase client while providing:
        • dry‑run behavior
        • embedding computation
        • typed upsert helpers for notes, notebooks, tags, and relationships

    The wrapper is designed for testability: any injected client that satisfies
    SupabaseClientInterface can be used (e.g., DummyClient in tests).
    """

    def __init__(
        self,
        client: Optional[SupabaseClientInterface] = None,
        dry_run: bool = False,
    ) -> None:
        """
        Initialize the SupabaseClient.

        Args:
            client:
                Optional injected client implementing SupabaseClientInterface.
                Used for tests or custom backends.

            dry_run:
                When True, no real Supabase calls are made. All upserts return
                deterministic fake values so the ingestion pipeline can run
                without touching external services.
        """
        self.dry_run = dry_run

        # If a client was injected (tests, stubs), use it.
        if client is not None:
            self.client = client
            return

        # If dry‑run, do not initialize a real Supabase client.
        if dry_run:
            self.client = None
            return

        # Otherwise, initialize the real Supabase client from environment variables.
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not key:
            raise RuntimeError(
                "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment."
            )

        self.client = create_client(url, key)

    def table(self, name: str) -> Any:
        """
        Proxy access to the underlying client's .table(name) method.

        Returns:
            A query builder object that supports:
                • upsert(record, on_conflict?)
                • select(...)
                • execute()
        """
        if not self.client:
            raise RuntimeError("Supabase client is not configured (dry‑run mode).")
        return self.client.table(name)

    def upsert_note_with_embedding(
        self,
        title: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
        id: Optional[str] = None,
        notebook_id: Optional[str] = None,
        table: str = "notes",
    ) -> Any:
        """
        Compute an embedding for the note body and upsert the note into Supabase.

        Args:
            title: The note title.
            body: The note body (required for embedding).
            metadata: Optional metadata dictionary.
            id: Optional note ID (used to enforce upsert behavior).
            notebook_id: Optional notebook foreign key.
            table: Supabase table name (default: "notes").

        Returns:
            The `.data` attribute from the Supabase response, or a deterministic
            fake record in dry‑run mode.

        Raises:
            ValueError: If body is empty.
            RuntimeError: If no client is provided in real mode.
        """
        if not body:
            raise ValueError("body must be provided")

        # ------------------------------------------------------------
        # Dry‑run mode:
        #     Skip embedding computation and database writes.
        #     Return a deterministic fake record so the orchestrator
        #     can proceed without touching Supabase.
        # ------------------------------------------------------------
        if self.dry_run:
            fake_embedding = [0.0] * 1536  # stable, predictable vector
            return {
                "id": id or f"dry-note-{title}",
                "title": title,
                "body": body,
                "metadata": metadata or {},
                "embedding": fake_embedding,
                "notebook_id": notebook_id,
            }

        # ------------------------------------------------------------
        # Real mode:
        #     Compute embedding and upsert into Supabase.
        # ------------------------------------------------------------
        if not self.client:
            raise RuntimeError(
                "No client provided to SupabaseClient. "
                "Please pass a valid client instance or use the default."
            )

        emb = compute_embedding(body)

        record: NoteRecord = {
            "title": title,
            "body": body,
            "metadata": metadata or {},
            "embedding": emb,
            "notebook_id": notebook_id,
        }

        if id:
            record["id"] = id

        # Upsert the note
        resp: SupabaseExecuteResponse = (
            self.client
            .table(table)
            .upsert(record)
            .execute()
        )

        # Defensive error handling for both attribute‑style and dict‑style responses
        error = getattr(resp, "error", None)
        if error:
            raise RuntimeError(f"Upsert error: {error}")

        # Normalize return shape
        if hasattr(resp, "data"):
            return resp.data
        if isinstance(resp, dict) and "data" in resp:
            return resp["data"]

        return resp

       # ------------------------------------------------------------
# SECTION 2 — Updated for ease of review
# ------------------------------------------------------------

        # ------------------------------------------------------------
        # Normalize return shape for real mode
        # ------------------------------------------------------------
        if hasattr(resp, "data"):
            return resp.data
        if isinstance(resp, dict) and "data" in resp:
            return resp["data"]

        # Fallback: return raw response (rare but safe)
        return resp

    # ------------------------------------------------------------------
    # Notebook Upserts
    # ------------------------------------------------------------------
    def upsert_notebooks(self, notebook_map: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """
        Upsert notebooks into the `notebooks` table.

        This method mirrors the tag upsert pattern:
            • deterministic dry‑run behavior
            • idempotent real‑mode upserts via `on_conflict="name"`
            • returns a canonical mapping of notebook_name -> notebook_id

        The orchestrator calls this before inserting notes so that
        note.notebook_id always references a valid, canonical notebook row.
        """
        if not notebook_map:
            return {}

        # Dry‑run: deterministic fake IDs
        if self.dry_run:
            return {name: f"dry-notebook-{name}" for name in notebook_map}

        payload = list(notebook_map.values())

        resp: SupabaseExecuteResponse = (
            self.client
            .table("notebooks")
            .upsert(payload, on_conflict="name")
            .execute()
        )

        # Normalize response
        data = getattr(resp, "data", None)
        if data is None and isinstance(resp, dict):
            data = resp.get("data", [])

        return {row["name"]: row["id"] for row in data}

    # ------------------------------------------------------------------
    # Tag Upserts
    # ------------------------------------------------------------------
    def upsert_tags(self, tags: list[str]) -> dict[str, str]:
        """
        Insert or update tags in the `tags` table.

        This method is intentionally idempotent:
        running ingestion multiple times will not create duplicate tags.
        Supabase enforces uniqueness via the `name` column.
        """
        if not tags:
            return {}

        unique_tags = list(set(tags))

        # Dry‑run: deterministic fake IDs
        if self.dry_run:
            return {t: f"dry-tag-{t}" for t in unique_tags}

        payload = [{"name": t} for t in unique_tags]

        resp: SupabaseExecuteResponse = (
            self.client
            .table("tags")
            .upsert(payload, on_conflict="name")
            .execute()
        )

        data = getattr(resp, "data", None)
        if data is None and isinstance(resp, dict):
            data = resp.get("data", [])

        return {row["name"]: row["id"] for row in data}

    # ------------------------------------------------------------------
    # Note‑Tag Relationship Upserts
    # ------------------------------------------------------------------
    def upsert_note_tag_relationships(
        self,
        note_id: str,
        tag_ids: list[str],
    ) -> None:
        """
        Create or update note‑tag relationships in the `note_tags` table.

        This method is intentionally idempotent:
        running ingestion multiple times will not create duplicate
        (note_id, tag_id) pairs. Supabase enforces this via a composite
        uniqueness constraint on (note_id, tag_id).
        """
        if not tag_ids:
            return

        # Dry‑run: no‑op but deterministic
        if self.dry_run:
            return

        payload = [{"note_id": note_id, "tag_id": tid} for tid in tag_ids]

        (
            self.client
            .table("note_tags")
            .upsert(payload, on_conflict="note_id,tag_id")
            .execute()
        )


# === Shared instance for application use ===

SUPABASE_URL = os.getenv("SUPABASE_URL", "http://localhost:54321")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "test-key")

real_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase: SupabaseClient = SupabaseClient(real_client)

__all__ = [
    "SupabaseClient",
    "supabase",
    "Executable",
    "SupabaseExecuteResponse",
    "TableQuery",
]