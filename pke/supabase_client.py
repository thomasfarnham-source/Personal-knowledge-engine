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
from typing import Any, Dict, List, Optional, cast

from supabase import Client, create_client  # Third‑party SDK
from pke.embedding import compute_embedding  # Local embedding helper
from pke.types import (
    NoteRecord,
    SupabaseClientInterface,
    Executable,
    SupabaseExecuteResponse,
    TableQuery,
    UpsertNoteRecord,
)
from pke.wrapped_supabase_client import WrappedSupabaseClient  # Used in production

# IMPORTANT DESIGN DECISION
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

        Parameters
        ----------
        client : SupabaseClientInterface | None
            Optional injected client implementing SupabaseClientInterface.
            Used for tests or custom backends.

        dry_run : bool
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
            raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment.")

        self.client = create_client(url, key)

    @classmethod
    def from_env(cls) -> "SupabaseClient":
        """
        Factory constructor that initializes a SupabaseClient using environment variables.

        Returns
        -------
        SupabaseClient
            A fully initialized SupabaseClient instance.
        """
        return cls(dry_run=False)

    # -----------------------------------------------------------------------
    # Notebook resolution ==== Part 2 ====
    # -----------------------------------------------------------------------

    def resolve_notebook_id(self, notebook_title: Optional[str]) -> Optional[str]:
        """
        Resolve the UUID of a notebook by title.

        Steps:
            1. If no title provided → return None.
            2. SELECT id FROM notebooks WHERE title = <title>.
            3. If exists → return id.
            4. If not → INSERT {title} and return new id.

        This method is intentionally conservative:
            • No assumptions about schema beyond "id" and "title".
            • No caching — correctness > performance.
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
            return None

        if not self.client:
            raise RuntimeError("Supabase client is not configured")

        # 1. Lookup existing notebook
        select_resp: SupabaseExecuteResponse = (
            self.client.table("notebooks").select("id").eq("title", notebook_title).execute()
        )

        rows = _extract_data(select_resp)
        if rows:
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

    # ------------------------------------------------------------


# SECTION 2 — Updated for ease of review
# ------------------------------------------------------------

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
        the UpsertNoteRecord TypedDict. In dry-run mode, returns a deterministic
        fake record without contacting Supabase.

    Raises
    ------
    ValueError
        If body is empty.
    RuntimeError
        If the underlying client is not configured or Supabase returns an error.
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
        return [
            {
                "id": id or f"dry-note-{title}",
                "title": title,
                "body": body,
                "metadata": metadata or {},
                "embedding": fake_embedding,
                "notebook_id": notebook_id,
            }
        ]

    # ------------------------------------------------------------
    # Real mode:
    #     Compute embedding and upsert into Supabase.
    # ------------------------------------------------------------
    if not self.client:
        raise RuntimeError(
            "No client provided to SupabaseClient. "
            "Please construct via SupabaseClient.from_env() or inject a valid client."
        )

    # Compute embedding for the note body.
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
    resp: SupabaseExecuteResponse = self.client.table(table).upsert(record).execute()

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


# SECTION 3 — Updated for ease of review
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
        self.client.table("notebooks").upsert(payload, on_conflict="name").execute()
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
        self.client.table("tags").upsert(payload, on_conflict="name").execute()
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

    self.client.table("note_tags").upsert(payload, on_conflict="note_id,tag_id").execute()


# === Shared instance for application use ===

SUPABASE_URL = os.getenv("SUPABASE_URL", "http://localhost:54321")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "test-key")

real_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase: SupabaseClient = SupabaseClient(real_client)

__all__ = [
    "SupabaseClient",
    "Executable",
    "SupabaseExecuteResponse",
    "TableQuery",
]
