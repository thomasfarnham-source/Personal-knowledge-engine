# ------------------------------------------------------------
# File break point 1
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

Milestone 8.8.2.2 refactors this client to align with the new ingestion pipeline:
    • explicit metadata fields (no nested metadata dicts in real mode)
    • deterministic dry‑run behavior
    • consistent error normalization
    • resource IDs stored directly on the note row

Option A: backward compatibility is preserved:
    • legacy `metadata` parameter is still accepted
    • dry‑run mode still exposes a `metadata` field for tests
    • legacy helpers (resolve_notebook_id, upsert_note) are retained
"""

from typing import Any, Dict, List, Optional, TypeVar, cast
from pke.embedding import compute_embedding
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

    This helper ensures deterministic behavior regardless of which client
    implementation is injected.
    """

    # Dict-style response (DummyClient, FailingClient, WrappedSupabaseClient)
    if isinstance(resp, dict):
        status = resp.get("status", 200)
        if status >= 400:
            raise RuntimeError(f"Supabase error: {resp}")
        data = resp.get("data", [])
        return cast(List[T], data)

    # SDK-style response
    error = getattr(resp, "error", None)
    if error:
        raise RuntimeError(f"Supabase error: {error}")

    data = getattr(resp, "data", None)
    if data is None:
        return []

    if isinstance(data, list):
        return cast(List[T], data)

    return cast(List[T], [data])


# ---------------------------------------------------------------------------
# Main wrapper class
# ---------------------------------------------------------------------------


class SupabaseClient:
    """
    A minimal, dependency‑injected wrapper around a Supabase‑compatible client.

    This class is intentionally thin: it forwards calls to the underlying
    Supabase client while providing:

        • deterministic dry‑run behavior
        • embedding computation
        • typed upsert helpers for notes, notebooks, tags, and relationships

    Milestone 8.8.2.2 updates this class to align with the new parser +
    orchestrator contract, which uses explicit metadata fields and a flat,
    ingestion‑ready schema, while preserving backward compatibility for
    existing tests and legacy callers.
    """

    def __init__(self, client: Any = None, dry_run: bool = False) -> None:
        """
        Initialize the SupabaseClient.

        Accepts `client: Any` because the real Supabase SDK does not implement
        our Protocol, and our test doubles vary in structure. Duck typing keeps
        the wrapper flexible while still allowing mypy to enforce structure at
        method boundaries.

        Parameters
        ----------
        client : Any
            A Supabase‑compatible client (real SDK, DummyClient, or test stub).
        dry_run : bool
            If True, forces dry‑run mode regardless of the provided client.
        """

        # Explicit dry-run override: caller forces no‑write behavior.
        if dry_run:
            self.dry_run = True
            self.client = None
            return

        # No client → real mode is impossible; caller must handle this.
        if client is None:
            self.dry_run = False
            self.client = None
            return

        # DummyClient → treat as dry-run for tests.
        if client.__class__.__name__ == "DummyClient":
            self.dry_run = True
            self.client = client
            return

        # Real Supabase client.
        self.dry_run = False
        self.client = client

    @classmethod
    def from_env(cls) -> "SupabaseClient":
        """
        Factory constructor for production usage.

        This placeholder currently returns an instance with no configured
        client. Callers are expected to inject a real Supabase client via
        the constructor in production code.

        This method is retained for API completeness and may be wired to
        environment‑based configuration in a future milestone.
        """
        return cls(dry_run=False)

    # -----------------------------------------------------------------------
    # Internal helper: enforce presence of a real Supabase client
    # -----------------------------------------------------------------------

    def _require_client(self) -> Any:
        """
        Return the configured Supabase client or raise a RuntimeError.

        This method exists to satisfy mypy: even though runtime guards ensure
        that real-mode code paths always have a client, mypy cannot infer that
        across method boundaries. Centralizing the check here keeps the code
        clean and avoids repeated type ignores.
        """
        if self.client is None:
            raise RuntimeError("Supabase client is not configured")
        return self.client

    # -----------------------------------------------------------------------
    # Notebook resolution (legacy helper)
    # -----------------------------------------------------------------------

    def resolve_notebook_id(self, notebook_title: Optional[str]) -> Optional[str]:
        """
        Resolve or create a notebook row by title.

        This method remains for backward compatibility but is not used by the
        new orchestrator, which performs notebook resolution in batch.

        Parameters
        ----------
        notebook_title : str | None
            The human‑readable notebook title.

        Returns
        -------
        str | None
            The resolved or newly created notebook ID, or None if no title
            was provided.

        Raises
        ------
        RuntimeError
            If the Supabase client is not configured or the insert returns
            no rows.
        """
        if not notebook_title:
            return None

        if not self.client:
            raise RuntimeError("Supabase client is not configured")

        # Lookup existing notebook by title.
        client = self._require_client()
        select_resp = client.table("notebooks").select("id").eq("title", notebook_title).execute()

        rows: List[Dict[str, Any]] = _extract_data(select_resp)
        if rows:
            return rows[0]["id"]

        # Insert a new notebook row.
        client = self._require_client()
        insert_resp = client.table("notebooks").insert({"title": notebook_title}).execute()

        # Normalize the insert response into a list of notebook-row dictionaries.
        # Notebook rows are plain dicts (not NoteRecord), so we annotate explicitly.
        inserted: List[Dict[str, Any]] = _extract_data(insert_resp)
        if not inserted:
            raise RuntimeError(f"Notebook insert returned no rows for title={notebook_title!r}")

        return inserted[0]["id"]

    # -----------------------------------------------------------------------
    # Note upsert with embedding (Milestone 8.8.2.2)
    # -----------------------------------------------------------------------

    def upsert_note_with_embedding(
        self,
        title: str,
        body: str,
        metadata: Dict[str, Any] | None = None,
        id: str | None = None,
        notebook_id: str | None = None,
        table: str = "notes",
    ) -> List[NoteRecord]:
        """
        Upsert a note into Supabase, computing an embedding for the body.

        Milestone 8.8.2.2 alignment:
        • explicit metadata fields replaced the old nested `metadata` dict
          in the real Supabase schema
        • `metadata` parameter is accepted only for backward compatibility
        • `id` and `notebook_id` are optional and may be generated/resolved upstream
        • resources are stored directly on the note row
        • dry‑run mode returns deterministic fake embeddings and fake IDs
        • real mode computes embeddings and performs a Supabase upsert
        • consistent error normalization across dict‑style and SDK‑style clients

        Parameters
        ----------
        title : str
            Human‑readable note title.
        body : str
            Main text content. Must be non‑empty.
        metadata : dict | None
            Legacy metadata dict. Accepted for compatibility with older tests.
            Ignored as a nested field in real mode because explicit fields now
            represent metadata.
        id : str | None
            Optional explicit note ID. If None, a UUID may be generated upstream.
        notebook_id : str | None
            Optional foreign key to the notebooks table.
        table : str
            Target Supabase table. Defaults to "notes".

        Returns
        -------
        list[NoteRecord]
            A list containing the upserted note record.

        Raises
        ------
        ValueError
            If `body` is empty.
        RuntimeError
            If real mode is requested but no Supabase client is configured.
        """
        # ------------------------------------------------------------
        # File break point 2
        # ------------------------------------------------------------

        # ------------------------------------------------------------
        # Guard: real mode requires a real client
        # ------------------------------------------------------------
        if not self.dry_run and self.client is None:
            raise RuntimeError("No client provided to SupabaseClient")

        if not body:
            raise ValueError("body must be provided")

        # ------------------------------------------------------------
        # Dry‑run mode: deterministic, no‑write behavior
        # ------------------------------------------------------------
        # In dry‑run mode we do NOT call Supabase or the embedding API.
        # Instead, we return a fully‑formed NoteRecord with:
        #   • a fake 1536‑dimensional embedding (all zeros)
        #   • the provided title/body/id/notebook_id
        #   • a compatibility "metadata" field (tests still expect it)
        #
        # This path is intentionally deterministic so contributors can
        # run CLI commands without network access and still validate
        # the shape of the returned record.
        # ------------------------------------------------------------
        if self.dry_run:
            fake_embedding = [0.0] * 1536

            # Cast to NoteRecord for type correctness while preserving the
            # backward‑compatible "metadata" field expected by tests.
            return [
                cast(
                    NoteRecord,
                    {
                        "id": id,
                        "title": title,
                        "body": body,
                        "embedding": fake_embedding,
                        "notebook_id": notebook_id,
                        # Backward‑compatibility for the test suite:
                        # The real ingestion schema no longer uses a nested
                        # metadata dict, but older tests still assert that
                        # this field exists. Including it here keeps dry‑run
                        # behavior predictable without polluting the real
                        # Supabase schema.
                        "metadata": metadata or {},
                    },
                )
            ]

        # ------------------------------------------------------------
        # Real mode: compute embedding + upsert
        # ------------------------------------------------------------
        # In real mode we compute the embedding using the configured
        # embedding provider, then build a NoteRecord using explicit
        # metadata fields (Milestone 8.8.2.2). No nested metadata dict
        # is stored in the database.
        # ------------------------------------------------------------
        emb = compute_embedding(body)

        # Build the row payload using explicit metadata fields.
        # Each field is pulled from the legacy metadata dict for
        # backward‑compatibility with older callers, but the schema
        # itself is now explicit and typed.
        record: NoteRecord = {
            "id": id,
            "title": title,
            "body": body,
            "embedding": emb,
            "notebook_id": notebook_id,
            "created_time": metadata.get("created_time") if metadata else None,
            "updated_time": metadata.get("updated_time") if metadata else None,
            "deleted_time": metadata.get("deleted_time") if metadata else None,
            "user_created_time": metadata.get("user_created_time") if metadata else None,
            "user_updated_time": metadata.get("user_updated_time") if metadata else None,
            "is_conflict": metadata.get("is_conflict") if metadata else None,
            "source": metadata.get("source") if metadata else None,
            "source_application": metadata.get("source_application") if metadata else None,
            "markup_language": metadata.get("markup_language") if metadata else None,
            "resources": metadata.get("resources", []) if metadata else [],
        }

        # Perform the upsert using the configured Supabase client.
        client = self._require_client()
        resp = client.table(table).upsert(record).execute()

        # Normalize errors and data across dict‑style and SDK‑style responses.
        rows = cast(List[NoteRecord], _extract_data(resp))
        return rows

    # ------------------------------------------------------------------
    # Notebook Upserts
    # ------------------------------------------------------------------
    def upsert_notebooks(self, notebook_map: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """
        Upsert notebooks into the `notebooks` table.

        Milestone 8.8.2.2:
            • consistent error normalization via _extract_data
            • deterministic dry‑run IDs
            • canonical mapping: notebook_name → notebook_id

        Parameters
        ----------
        notebook_map : dict[str, dict[str, Any]]
            Mapping of notebook name to notebook payload.

        Returns
        -------
        dict[str, str]
            Mapping of notebook name to resolved notebook ID.
        """
        if not notebook_map:
            return {}

        if self.dry_run:
            # Deterministic fake IDs for dry‑run mode.
            return {name: f"dry-notebook-{name}" for name in notebook_map}

        payload = list(notebook_map.values())
        client = self._require_client()
        resp = client.table("notebooks").upsert(payload, on_conflict="name").execute()

        rows: List[Dict[str, Any]] = _extract_data(resp)
        return {row["name"]: row["id"] for row in rows}

    # ------------------------------------------------------------------
    # Tag Upserts
    # ------------------------------------------------------------------
    def upsert_tags(self, tags: List[str]) -> Dict[str, str]:
        """
        Insert or update tags in the `tags` table.

        Idempotent by design — Supabase enforces uniqueness on `name`.

        Parameters
        ----------
        tags : list[str]
            A list of tag names.

        Returns
        -------
        dict[str, str]
            Mapping of tag name to tag ID.
        """
        if not tags:
            return {}

        # Deduplicate tags to avoid redundant upserts.
        unique_tags = list(set(tags))

        if self.dry_run:
            # Deterministic fake IDs for dry‑run mode.
            return {t: f"dry-tag-{t}" for t in unique_tags}

        payload = [{"name": t} for t in unique_tags]
        client = self._require_client()
        resp = client.table("tags").upsert(payload, on_conflict="name").execute()

        rows: List[Dict[str, Any]] = _extract_data(resp)
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

        Idempotent: Supabase enforces uniqueness on (note_id, tag_id).

        Parameters
        ----------
        note_id : str
            The ID of the note.
        tag_ids : list[str]
            A list of tag IDs to associate with the note.

        Raises
        ------
        RuntimeError
            If the Supabase client reports an error in real mode.
        """
        if not tag_ids:
            return

        if self.dry_run:
            # Relationships are not persisted in dry‑run mode.
            return

        payload = [{"note_id": note_id, "tag_id": tid} for tid in tag_ids]
        client = self._require_client()
        resp = client.table("note_tags").upsert(payload, on_conflict="note_id,tag_id").execute()

        # Normalize via _extract_data to surface any Supabase errors.
        # We intentionally ignore the returned rows; only failures matter here.
        _extract_data(resp)

    # ------------------------------------------------------------------
    # Direct Note Upsert (rarely used; kept for compatibility)
    # ------------------------------------------------------------------
    def upsert_note(self, payload: dict) -> NoteRecord:
        """
        Upsert a single note row into the `notes` table.

        This method is retained for compatibility with older ingestion flows.
        The new orchestrator uses upsert_note_with_embedding instead.

        Parameters
        ----------
        payload : dict
            A raw note payload matching the `notes` table schema.

        Returns
        -------
        NoteRecord
            The upserted note row.

        Raises
        ------
        RuntimeError
            If the Supabase client reports an error or returns an unexpected
            data format.
        """
        client = self._require_client()
        response = client.table("notes").upsert(payload, returning="representation").execute()

        # Reuse the shared normalization helper for consistency.
        rows = cast(List[NoteRecord], _extract_data(response))
        if not rows:
            raise RuntimeError("Supabase upsert returned no rows.")

        # For this legacy helper we return the first row only.
        return rows[0]
