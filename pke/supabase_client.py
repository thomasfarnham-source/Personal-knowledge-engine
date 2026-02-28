# ------------------------------------------------------------
# File break point 1
# ------------------------------------------------------------
"""
Supabase client wrapper for ingestion.

This wrapper provides a stable, typed interface for interacting with Supabase
during ingestion. It supports:

    • real mode (using the Supabase Python client)
    • dry‑run mode (deterministic, no‑write behavior for testing)

Design goals:

    • Single, explicit contract for the orchestrator:
        - real mode: return "inserted" or "updated"
        - dry‑run mode: return [NoteRecord] for structural assertions

    • Deterministic behavior:
        - same inputs → same outputs (especially in tests)

    • Clear separation of concerns:
        - orchestrator owns sequencing and pipeline logic
        - SupabaseClient owns persistence and insert/update detection

    • Test alignment:
        - MockSupabaseClient and real SupabaseClient share the same contract
"""

from typing import Any, Dict, List, Optional, TypeVar, cast

from pke.embedding.embedding_client import EmbeddingClient
from pke.types import NoteRecord

T = TypeVar("T", bound=Dict[str, Any])


# ---------------------------------------------------------------------------
# Helper: normalize Supabase responses
# ---------------------------------------------------------------------------
def _extract_data(resp: Any) -> List[T]:
    """
    Normalize Supabase responses across:
        • real SDK objects
        • DummyClient-style dicts
        • test stubs

    Always returns a list of row dictionaries.
    Raises RuntimeError on any Supabase error.

    Why this exists:
        Different Supabase client implementations (real SDK, DummyClient,
        wrapped clients in tests) expose slightly different response shapes.
        This helper collapses them into a single, predictable structure so
        the rest of the code can treat "data" as List[dict] without caring
        about the underlying client.
    """

    # Dict-style response (DummyClient, FailingClient, WrappedSupabaseClient)
    if isinstance(resp, dict):
        status = resp.get("status", 200)
        if status >= 400:
            # Surface the entire response for debugging; callers don't need
            # to know the exact shape, only that Supabase reported an error.
            raise RuntimeError(f"Supabase error: {resp}")
        data = resp.get("data", [])
        return cast(List[T], data)

    # SDK-style response: look for an "error" attribute first
    error = getattr(resp, "error", None)
    if error:
        raise RuntimeError(f"Supabase error: {error}")

    # Then normalize the "data" attribute
    data = getattr(resp, "data", None)
    if data is None:
        return []

    if isinstance(data, list):
        return cast(List[T], data)

    # Some clients return a single row dict instead of a list
    return cast(List[T], [data])


# ---------------------------------------------------------------------------
# Main wrapper class
# ---------------------------------------------------------------------------
class SupabaseClient:
    """
    A minimal, dependency‑injected wrapper around a Supabase‑compatible client.

    Responsibilities:
        • Provide a single, stable contract for ingestion:
            - upsert_note_with_embedding(...)
            - upsert_notebooks(...)
            - upsert_tags(...)
            - upsert_note_tag_relationships(...)

        • Hide Supabase response quirks behind _extract_data

        • Expose a deterministic embedding_client for the orchestrator

    Non‑responsibilities:
        • Orchestrating ingestion stages
        • Implementing history/versioning
        • Managing business logic beyond "inserted vs updated"
    """

    def __init__(
        self,
        client: Any = None,
        dry_run: bool = False,
        embedding_client: Optional[EmbeddingClient] = None,
    ) -> None:
        """
        Initialize the SupabaseClient.

        Parameters
        ----------
        client : Any
            A Supabase‑compatible client (real SDK, DummyClient, or test stub).
        dry_run : bool
            If True, forces dry‑run mode regardless of the provided client.
        embedding_client : EmbeddingClient | None
            Optional injection of a custom embedding provider.
            If omitted, a deterministic provider is used.

        Design notes:
            • embedding_client is injected to keep this wrapper agnostic to
              the underlying embedding provider while still giving tests a
              deterministic default.

            • dry_run short‑circuits real network I/O and is used both for
              tests and for CLI "preview" modes.
        """

        # Embedding client setup:
        #   - If none is provided, use a deterministic provider so tests and
        #     local runs are reproducible.
        if embedding_client is None:
            self.embedding_client = EmbeddingClient(provider="deterministic")
        else:
            self.embedding_client = embedding_client

        # Explicit dry‑run override:
        #   - When dry_run=True, we never talk to a real Supabase backend.
        if dry_run:
            self.dry_run = True
            self.client = None
            return

        # No client provided:
        #   - This is allowed, but only in contexts where the caller knows
        #     they will not perform real writes (e.g., some tests).
        self.client = client

        # DummyClient is treated as a dry‑run backend:
        #   - It behaves like Supabase but does not persist to a real DB.
        if client is not None and client.__class__.__name__ == "DummyClient":
            self.dry_run = True
        else:
            # Real Supabase client or None (non‑dry‑run but unusable for writes)
            self.dry_run = False

    @classmethod
    def from_env(cls) -> "SupabaseClient":
        """
        Factory constructor placeholder for production.

        In a real deployment, this would:
            • read environment variables
            • construct the real Supabase client
            • inject it into this wrapper

        For now, it simply returns a non‑dry‑run instance with no client,
        serving as a placeholder for future wiring.
        """
        return cls(dry_run=False)

    def _require_client(self) -> Any:
        """
        Internal guard to ensure a real Supabase client is available.

        Used in all code paths that must talk to Supabase. Raises a clear
        RuntimeError if the client is missing instead of failing deeper in
        the call stack.
        """
        if self.client is None:
            raise RuntimeError("Supabase client is not configured")
        return self.client

    # ------------------------------------------------------------
    # File break point 2
    # ------------------------------------------------------------

    # -----------------------------------------------------------------------
    # Legacy notebook resolver (kept only for backward compatibility)
    # -----------------------------------------------------------------------
    def resolve_notebook_id(self, notebook_title: Optional[str]) -> Optional[str]:
        """
        Legacy helper for older ingestion flows.

        The new orchestrator no longer calls this; it performs notebook
        upserts in batch via upsert_notebooks. This method is retained only
        so older code paths (or ad‑hoc scripts) do not break.

        Behavior:
            • If notebook_title is falsy → return None
            • Else:
                - look up an existing notebook by title
                - if found, return its id
                - if not found, insert a new notebook and return its id
        """
        if not notebook_title:
            return None

        client = self._require_client()

        # Lookup existing notebook by title
        select_resp = client.table("notebooks").select("id").eq("title", notebook_title).execute()
        rows: list[dict[str, Any]] = _extract_data(select_resp)

        if rows:
            return rows[0]["id"]
        # Insert new notebook if none exists
        insert_resp = client.table("notebooks").insert({"title": notebook_title}).execute()
        inserted: list[dict[str, Any]] = _extract_data(insert_resp)

        if not inserted:
            # Defensive: Supabase should always return the inserted row
            raise RuntimeError(f"Notebook insert returned no rows for title={notebook_title!r}")

        return inserted[0]["id"]

    # -----------------------------------------------------------------------
    # Note upsert with embedding (modern ingestion path)
    # -----------------------------------------------------------------------
    def upsert_note_with_embedding(
        self,
        *,
        id: str,
        title: str,
        body: str,
        metadata: Dict[str, Any] | None,
        notebook_id: Optional[str],
        embedding: List[float],
        table: str = "notes",
    ) -> str | list[NoteRecord]:
        """
        Upsert a note into Supabase using a precomputed embedding.

        Contract (Option B1):

            • In REAL mode:
                - Returns "inserted" if the note did not exist before
                - Returns "updated" if the note already existed

            • In DRY‑RUN mode:
                - Returns [NoteRecord] so tests can assert on structure

        Why this split exists:
            • The orchestrator needs a simple "inserted vs updated" signal
              in real mode to maintain accurate ingestion metrics.

            • Tests need a concrete NoteRecord shape in dry‑run mode to
              validate payload structure without hitting a real DB.
        """

        # Guard: in real mode, a client must be present
        if not self.dry_run and self.client is None:
            raise RuntimeError("No client provided to SupabaseClient")

        if not body:
            # Body is required for both embedding generation and storage
            raise ValueError("body must be provided")

        # ------------------------------------------------------------
        # DRY‑RUN MODE — deterministic, no-write, test-aligned
        # ------------------------------------------------------------
        if self.dry_run:
            # In dry‑run, we simulate the NoteRecord that would be written.
            # We keep metadata as a nested dict so tests can assert on it
            # directly without needing to know the full column schema.
            record: NoteRecord = {
                "id": id,
                "title": title,
                "body": body,
                "embedding": embedding,
                "notebook_id": notebook_id,
                "metadata": metadata or {},
            }
            # Tests expect a list containing a single NoteRecord.
            return [record]

        # ------------------------------------------------------------
        # REAL MODE — return "inserted" or "updated"
        # ------------------------------------------------------------
        client = self._require_client()

        # Step 1: determine whether the note already exists.
        # This is a cheap select by primary key and is required to decide
        # whether we report "inserted" or "updated" to the orchestrator.
        existing = client.table(table).select("id").eq("id", id).execute()
        note_exists = bool(_extract_data(existing))

        # Step 2: build the row payload.
        # We keep metadata as a nested dict here as well; if you later decide
        # to denormalize metadata into explicit columns, this is the single
        # place to change.
        payload: NoteRecord = {
            "id": id,
            "title": title,
            "body": body,
            "embedding": embedding,
            "notebook_id": notebook_id,
            "metadata": metadata or {},
        }

        # Step 3: perform the upsert.
        # Supabase will:
        #   • insert a new row if id does not exist
        #   • update the existing row if id already exists
        resp = client.table(table).upsert(payload).execute()
        _extract_data(resp)  # surface any errors

        # Step 4: return a simple status string for the orchestrator.
        # This is the core of Option B1: the orchestrator does not need the
        # record itself, only whether it was inserted or updated.
        return "updated" if note_exists else "inserted"

    # ------------------------------------------------------------------
    # Notebook Upserts (modern ingestion path)
    # ------------------------------------------------------------------
    def upsert_notebooks(self, notebook_map: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """
        Upsert notebooks into the `notebooks` table.

        Input:
            notebook_map:
                { "<title>": {"title": "<title>"} }

        Returns:
            { "<title>": "<id>" }

        Design:
            • The orchestrator builds notebook_map from parsed notes.
            • This method performs a batch upsert and returns a mapping
              from notebook title to its Supabase id.
        """

        if not notebook_map:
            # No notebooks to upsert → empty mapping
            return {}

        # Dry‑run mode: generate deterministic fake IDs so tests can assert
        # on downstream behavior without hitting a real DB.
        if self.dry_run:
            return {name: f"dry-notebook-{name}" for name in notebook_map}

        # Normalize payloads into a list of row dicts
        payload = [{"title": name} for name in notebook_map]

        client = self._require_client()
        resp = client.table("notebooks").upsert(payload, on_conflict="title").execute()

        rows: list[dict[str, Any]] = _extract_data(resp)
        # Build a mapping from notebook title to its Supabase id
        return {row["title"]: row["id"] for row in rows}

    # ------------------------------------------------------------------
    # Tag Upserts
    # ------------------------------------------------------------------
    def upsert_tags(self, tags: List[str]) -> Dict[str, str]:
        """
        Insert or update tags in the `tags` table.

        Input:
            tags: list of raw tag strings (may contain duplicates/whitespace)

        Returns:
            { "<tag>": "<id>" }

        Design:
            • Tags are normalized (trimmed, deduplicated, sorted) before
              upsert to avoid noisy duplicates.
            • Dry‑run mode returns deterministic fake IDs.
        """

        if not tags:
            return {}

        # Normalize tags: strip whitespace, drop empties, deduplicate, sort
        unique_tags = sorted({t.strip() for t in tags if t and t.strip()})

        if self.dry_run:
            # Deterministic fake IDs for tests and dry‑run CLI
            return {t: f"dry-tag-{t}" for t in unique_tags}

        payload = [{"name": t} for t in unique_tags]

        client = self._require_client()
        resp = client.table("tags").upsert(payload, on_conflict="name").execute()

        rows: list[dict[str, Any]] = _extract_data(resp)
        # Map tag name → Supabase id
        return {row["name"]: row["id"] for row in rows}

    # ------------------------------------------------------------
    # File break point 3
    # ------------------------------------------------------------

    # ------------------------------------------------------------------
    # Note‑Tag Relationship Upserts
    # ------------------------------------------------------------------
    def upsert_note_tag_relationships(self, note_id: str, tag_ids: List[str]) -> None:
        """
        Create or update note‑tag relationships in the `note_tags` table.

        Input:
            note_id: Supabase id of the note
            tag_ids: list of Supabase tag ids to associate with the note

        Idempotency:
            • Supabase enforces uniqueness on (note_id, tag_id) via
              on_conflict="note_id,tag_id".
            • Calling this multiple times with the same pairs is safe.

        Dry‑run:
            • No‑op; relationships are not persisted, but the orchestrator
              still increments its counters based on the input.
        """

        if not tag_ids:
            # Nothing to relate → nothing to do
            return

        if self.dry_run:
            # Dry‑run: do not touch Supabase; orchestrator already counted
            return

        # Build the relationship payload: one row per (note_id, tag_id) pair
        payload = [{"note_id": note_id, "tag_id": tid} for tid in tag_ids]

        client = self._require_client()
        resp = client.table("note_tags").upsert(payload, on_conflict="note_id,tag_id").execute()

        _extract_data(resp)  # surface errors, ignore returned rows

    # ------------------------------------------------------------------
    # Direct Note Upsert (legacy helper)
    # ------------------------------------------------------------------
    def upsert_note(self, payload: dict) -> NoteRecord:
        """
        Legacy helper for older ingestion flows.

        The new orchestrator uses upsert_note_with_embedding instead, which
        is embedding‑aware and returns a simple status string in real mode.

        This method is retained for compatibility with existing code that
        expects a direct NoteRecord from Supabase.
        """

        client = self._require_client()
        response = client.table("notes").upsert(payload, returning="representation").execute()

        rows = cast(List[NoteRecord], _extract_data(response))
        if not rows:
            # Defensive: Supabase should always return the upserted row
            raise RuntimeError("Supabase upsert returned no rows.")

        return rows[0]
