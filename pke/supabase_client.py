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

from typing import Any, Dict, List, Optional, cast
from pke.embedding import compute_embedding  # Local embedding helper
from pke.types import (
    NoteRecord,
)

# IMPORTANT DESIGN DECISION
# We intentionally do NOT type the injected client as SupabaseClientInterface.
# The real Supabase SDK client does NOT implement our Protocol (it lacks .list, .upsert),
# and mypy will reject it. Instead, we accept Any and rely on duck typing.
#
# The Protocol still exists in pke.types for tests, stubs, and future real-client wrappers.


# ---------------------------------------------------------------------------
# Helper: normalize Supabase responses
# ---------------------------------------------------------------------------


def _extract_data(resp: Any) -> List[NoteRecord]:
    """
    Normalize Supabase responses across:
        • real SDK objects
        • DummyClient-style dicts
        • test stubs

    Always returns a list of row dictionaries.

    Raises RuntimeError on any Supabase error.

    NOTE:
    The real Supabase SDK exposes attributes (.data, .error),
    while our test doubles return dictionaries. We normalize both
    into a SupabaseExecuteResponse-like dict and then extract "data".
    """

    # Case 1: DummyClient-style dict
    if isinstance(resp, dict):
        status = resp.get("status", 200)
        if status >= 400:
            raise RuntimeError(f"Supabase error: {resp}")
        return cast(List[NoteRecord], resp.get("data", []))

    # Case 2: Real Supabase SDK object (dynamic attributes)
    error = getattr(resp, "error", None)
    if error:
        raise RuntimeError(f"Supabase error: {error}")

    data = getattr(resp, "data", None)
    return cast(List[NoteRecord], data or [])


# ---------------------------------------------------------------------------
# Main wrapper class
# ---------------------------------------------------------------------------


class SupabaseClient:
    """
    A minimal, dependency‑injected wrapper around a Supabase‑compatible client.

    This class is intentionally thin: it forwards calls to the underlying
    Supabase client while providing:

        • dry‑run behavior
        • embedding computation
        • typed upsert helpers for notes, notebooks, tags, and relationships

    The wrapper is designed for testability and flexibility. Any injected client
    may be used — the real Supabase SDK, WrappedSupabaseClient, DummyClient,
    FakeClient, or FailingClient. Because these clients do not share a common
    base class, the constructor accepts `Any` and relies on Protocol‑based
    structural typing at call sites.
    """

    def __init__(
        self,
        client: Any = None,
        dry_run: bool = False,
    ) -> None:
        """
        Initialize the SupabaseClient.

        This constructor intentionally accepts `client: Any` rather than
        `SupabaseClientInterface`. The real Supabase Python client does not
        implement our Protocol, and our test doubles vary in structure. Using
        `Any` preserves flexibility while still allowing mypy to enforce
        Protocol compatibility where it matters — at the method boundaries.
        """

        self.dry_run = dry_run

        # If a client was injected (tests, stubs, or a real Supabase client),
        # use it directly. This path bypasses environment variable loading.
        self.client = client

    @classmethod
    def from_env(cls) -> "SupabaseClient":
        """
        Factory constructor that initializes a SupabaseClient using environment
        variables. This is the preferred entry point for production code.
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
        """
        if not notebook_title:
            return None

        if not self.client:
            raise RuntimeError("Supabase client is not configured")

        # 1. Lookup existing notebook
        select_resp: Any = (
            self.client.table("notebooks").select("id").eq("title", notebook_title).execute()
        )

        rows = _extract_data(select_resp)
        if rows:
            return rows[0]["id"]

        # 2. Insert new notebook
        insert_payload: Dict[str, Any] = {"title": notebook_title}

        insert_resp: Any = self.client.table("notebooks").insert(insert_payload).execute()

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
    ) -> List[NoteRecord]:
        """
        Upsert a note into the given table, computing an embedding for the body.

        This method provides a stable, typed interface for inserting or updating
        notes in Supabase. It supports both real mode (actual Supabase writes)
        and dry‑run mode (deterministic, no‑write behavior for testing).

        Returns a list of NoteRecord rows, matching the normalized shape of
        SupabaseExecuteResponse["data"].
        """

        # ----------------------------------------------------------------------
        # Guard: real mode requires a configured client.
        # Tests explicitly expect the constructor to allow client=None, so the
        # method—not __init__—must enforce this invariant.
        # ----------------------------------------------------------------------
        if self.client is None and not self.dry_run:
            raise RuntimeError("No client provided to SupabaseClient")

        # Body is required in both real and dry‑run modes.
        if not body:
            raise ValueError("body must be provided")

        # ----------------------------------------------------------------------
        # Dry‑run mode:
        #     Skip embedding computation and database writes.
        #     Return a deterministic fake record so the orchestrator can proceed
        #     without touching Supabase.
        # ----------------------------------------------------------------------
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

        # ----------------------------------------------------------------------
        # Real mode:
        #     Compute embedding and upsert into Supabase.
        # ----------------------------------------------------------------------

        # Compute embedding for the note body.
        emb = compute_embedding(body)

        # Build the NoteRecord payload.
        record: NoteRecord = {
            "title": title,
            "body": body,
            "metadata": metadata or {},
            "embedding": emb,
            "notebook_id": notebook_id,
        }

        if id:
            record["id"] = id

        # Perform the upsert.
        # The return value may be:
        #   • a dict (DummyClient, FailingClient, WrappedSupabaseClient)
        #   • a dynamic SDK object with .data and .error attributes
        resp: Any = self.client.table(table).upsert(record).execute()

        # ----------------------------------------------------------------------
        # Normalize errors across dict-style and SDK-style responses.
        # ----------------------------------------------------------------------
        if isinstance(resp, dict):
            # Dict-style error handling
            if resp.get("status", 200) >= 400:
                raise RuntimeError(f"Upsert error: {resp}")
            return cast(List[NoteRecord], resp.get("data", []))

        # SDK-style: resp.error / resp.data
        error = getattr(resp, "error", None)
        if error:
            raise RuntimeError(f"Upsert error: {error}")

        data = getattr(resp, "data", None)
        return cast(List[NoteRecord], data or [])

    # ------------------------------------------------------------
    # SECTION 3 — Updated for ease of review
    # ------------------------------------------------------------

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

        resp: Any = self.client.table("notebooks").upsert(payload, on_conflict="name").execute()

        # Normalize dict-style and SDK-style responses
        if isinstance(resp, dict):
            if resp.get("status", 200) >= 400:
                raise RuntimeError(f"Notebook upsert error: {resp}")
            rows = resp.get("data", [])
        else:
            error = getattr(resp, "error", None)
            if error:
                raise RuntimeError(f"Notebook upsert error: {error}")
            rows = getattr(resp, "data", None) or []

        return {row["name"]: row["id"] for row in rows}

    # ------------------------------------------------------------------
    # Tag Upserts
    # ------------------------------------------------------------------
    def upsert_tags(self, tags: List[str]) -> Dict[str, str]:
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

        resp: Any = self.client.table("tags").upsert(payload, on_conflict="name").execute()

        # Normalize dict-style and SDK-style responses
        if isinstance(resp, dict):
            if resp.get("status", 200) >= 400:
                raise RuntimeError(f"Tag upsert error: {resp}")
            rows = resp.get("data", [])
        else:
            error = getattr(resp, "error", None)
            if error:
                raise RuntimeError(f"Tag upsert error: {error}")
            rows = getattr(resp, "data", None) or []

        return {row["name"]: row["id"] for row in rows}

    # ------------------------------------------------------------------
    # Note‑Tag Relationship Upserts
    # ------------------------------------------------------------------
    def upsert_note_tag_relationships(
        self,
        note_id: str,
        tag_ids: List[str],
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

        # We intentionally ignore the response — relationships are side‑effect only.
        resp: Any = (
            self.client.table("note_tags").upsert(payload, on_conflict="note_id,tag_id").execute()
        )

        # Normalize errors for consistency with other upsert helpers
        if isinstance(resp, dict):
            if resp.get("status", 200) >= 400:
                raise RuntimeError(f"Note‑tag upsert error: {resp}")
        else:
            error = getattr(resp, "error", None)
            if error:
                raise RuntimeError(f"Note‑tag upsert error: {error}")
