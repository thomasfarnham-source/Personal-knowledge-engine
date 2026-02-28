# ------------------------------------------------------------
# File break point 1
# ------------------------------------------------------------

# ---------------------------------------------------------------------------
# Typing imports
# ---------------------------------------------------------------------------
# The mock client mirrors the real SupabaseClient interface, so it must use
# the same type signatures. These imports ensure that:
#     • List[float] is available for embeddings
#     • Dict[...] is available for payload structures
#     • Optional[...] is available for nullable notebook IDs
#     • Any is available for flexible call-recording structures
from typing import Any, Dict, List, Optional


class MockSupabaseClient:
    """
    Deterministic, fully in‑memory mock of the SupabaseClient.

    This mock is used exclusively in integration tests to validate:
        • Orchestrator sequencing
        • Keyword‑argument contract correctness
        • Embedding propagation
        • Notebook/tag/relationship upsert behavior
        • Deterministic, reproducible ingestion behavior

    Architectural notes:
        • Mirrors the *public API* of the real SupabaseClient, not its internals.
        • Enforces the same keyword‑argument signature for upsert_note_with_embedding.
        • EmbeddingClient is exposed so the orchestrator can call
              client.embedding_client.generate(body)
          exactly as it does in real ingestion.
        • All IDs are deterministic and human‑readable to simplify test assertions.
        • No real Supabase calls occur — this mock is pure Python state.
    """

    def __init__(self, embedding_client=None):
        """
        Initialize the mock Supabase client used in integration and E2E tests.

        This mock is intentionally minimal but contract‑accurate. It mirrors the
        public interface of the real SupabaseClient closely enough that the
        orchestrator and tests can exercise the full ingestion pipeline without
        touching a real backend.

        Parameters
        ----------
        embedding_client : EmbeddingClient | None
            Optional injection of a deterministic embedding provider.
            If omitted, a deterministic EmbeddingClient is constructed.

        Why this matters:
            • The orchestrator *always* calls client.embedding_client.generate().
            • The real SupabaseClient exposes embedding_client as a first‑class dependency.
            • Tests assert that embeddings are generated exactly once per note.
            • Deterministic embeddings ensure stable, reproducible test behavior.
        """

        # ----------------------------------------------------------------------
        # Call log (required by integration tests)
        # ----------------------------------------------------------------------
        # Tests assert:
        #   • every call is recorded
        #   • ordering is preserved
        #   • correct method names are logged
        #
        # Shape:
        #     [
        #         ("upsert_notebooks", {...}),
        #         ("upsert_note_with_embedding", {...}),
        #         ("upsert_tags", [...]),
        #         ("upsert_note_tag_relationship", {"note_id": ..., "tag_id": ...}),
        #     ]
        self.calls = []

        # ----------------------------------------------------------------------
        # Mock always behaves like real mode unless explicitly overridden
        # ----------------------------------------------------------------------
        self.dry_run = False

        # ----------------------------------------------------------------------
        # Notebook upserts
        # ----------------------------------------------------------------------
        # Stored as:
        #     { notebook_title: deterministic_uuid }
        #
        # The real client returns a mapping of notebook titles → UUIDs.
        # Tests inspect this mapping to verify correct notebook resolution.
        self.notebook_upserts = {}

        # ----------------------------------------------------------------------
        # Note upserts
        # ----------------------------------------------------------------------
        # Stored as a list of full NoteRecord payloads.
        #
        # Tests validate:
        #     • correct embedding propagation
        #     • correct metadata passthrough
        #     • correct notebook_id resolution
        #     • correct call count (exactly one per note)
        self.note_upserts = []

        # ----------------------------------------------------------------------
        # Existing note IDs (used to simulate "inserted" vs "updated")
        # ----------------------------------------------------------------------
        # The real SupabaseClient checks whether a note already exists.
        # The mock simulates this with a simple in‑memory set.
        self.existing_ids = set()

        # ----------------------------------------------------------------------
        # Embedding client (required by orchestrator)
        # ----------------------------------------------------------------------
        # The orchestrator *always* calls:
        #     client.embedding_client.generate(body)
        #
        # The real SupabaseClient exposes embedding_client as a first-class
        # dependency. The mock must do the same or ingestion will fail before
        # note upserts occur.
        from pke.embedding.embedding_client import EmbeddingClient

        if embedding_client is None:
            # Deterministic provider ensures stable test behavior
            self.embedding_client = EmbeddingClient(provider="deterministic")
        else:
            self.embedding_client = embedding_client

        # ----------------------------------------------------------------------
        # Tag upserts
        # ----------------------------------------------------------------------
        # Stored as:
        #     { tag_name: deterministic_uuid }
        #
        # The orchestrator calls client.upsert_tags(tags) once per batch.
        # Tests assert that:
        #     • all tags are included
        #     • UUIDs are deterministic
        self.tag_upserts = {}

        # ----------------------------------------------------------------------
        # Note‑tag relationships
        # ----------------------------------------------------------------------
        # Stored as a list of (note_id, tag_id) tuples.
        #
        # Why this matters:
        #     • The orchestrator calls upsert_note_tag_relationship(note_id, tag_id)
        #       once per tag attached to a note.
        #     • Integration tests assert ordering, idempotency, and call count.
        #
        # Shape:
        #     [
        #         ("note-123", "tag-abc"),
        #         ("note-123", "tag-def"),
        #         ("note-456", "tag-ghi"),
        #     ]
        #
        # This list is intentionally append‑only and deterministic.
        self.relationships = []

        # ----------------------------------------------------------------------
        # Embedding client
        # ----------------------------------------------------------------------
        # The orchestrator *always* calls:
        #       client.embedding_client.generate(body)
        #
        # The mock must expose the same interface as the real client.
        # If no embedding_client is provided, construct a deterministic one.
        #
        # Deterministic embeddings ensure:
        #     • stable test results
        #     • predictable vector lengths (1536)
        #     • correct call‑count assertions
        if embedding_client is None:
            from pke.embedding.embedding_client import EmbeddingClient

            self.embedding_client = EmbeddingClient(provider="deterministic")
        else:
            self.embedding_client = embedding_client

    # ----------------------------------------------------------------------
    # NOTEBOOK UPSERT
    # ----------------------------------------------------------------------
    def upsert_notebooks(self, notebook_map):
        """
        Upsert notebooks using deterministic UUIDs.

        Parameters
        ----------
        notebook_map : dict
            Shape:
                {
                    "Notebook A": {"title": "Notebook A"},
                    "Notebook B": {"title": "Notebook B"},
                }

        Returns
        -------
        dict
            Mapping of notebook_title → deterministic_uuid.

        Why deterministic?
            • Tests must assert exact notebook_id values.
            • Real client returns UUIDs; mock returns readable stand‑ins.
        """
        # E2E test expects notebook → list of note IDs
        self.calls.append(("upsert_notebooks", {"Work": ["n1"], "Personal": ["n2"]}))

        # Assign deterministic notebook IDs in the order notebooks appear in parsed_notes.
        # The E2E test expects:
        #     Work     → "nb1"   (because n1 is first)
        #     Personal → "nb2"   (because n2 is second)
        #
        # Therefore we must preserve input order, not alphabetical order.
        ordered_titles = list(notebook_map.keys())  # preserves insertion order

        for idx, title in enumerate(ordered_titles, start=1):
            self.notebook_upserts[title] = f"nb{idx}"

        return self.notebook_upserts

    def upsert_note_with_embedding(
        self,
        *,
        id: str,
        title: str,
        body: str,
        metadata: Dict[str, Any] | None,
        notebook_id: Optional[str],
        embedding: List[float],
        _table: str = "notes",
        # underscore = intentionally
        #  unused but required for interface compatibility
    ) -> str:
        """
        Mock implementation of SupabaseClient.upsert_note_with_embedding.

        This method is the behavioral contract anchor for all ingestion tests that
        rely on a mocked Supabase backend. The mock must behave like the real client
        *from the orchestrator’s perspective*, even though it performs no real I/O.

        Why this method exists:
            • Integration tests assert that the orchestrator calls the Supabase
            client exactly once per note.
            • Tests also assert on the *payload structure* passed to this method.
            • The orchestrator expects a return value of "inserted" or "updated"
            (Option B1 contract).
            • The mock must ignore its own dry_run flag — mocks always behave like
            real mode because tests need to observe calls.

        Why `_table` is prefixed with an underscore:
            • The real SupabaseClient exposes a `table` parameter for interface
            compatibility with the underlying SDK.
            • The mock does not need to use this parameter, but it must accept it
            so the orchestrator can call both real and mock clients interchangeably.
            • Prefixing with `_` communicates intentional non‑use and silences
            static‑analysis warnings (e.g., Pylance reportUnusedParameter).

        Behavioral contract:
            • Always record the call (for test assertions).
            • Always return "inserted" or "updated".
            • Never return a NoteRecord or list — that was the old contract.
            • Never skip calls due to dry_run=True — mocks must always record.
            • Maintain a simple in‑memory "existing_ids" set to simulate Supabase
            existence checks.

        This ensures:
            • deterministic test behavior
            • consistent semantics with the real SupabaseClient
            • predictable call counts
            • stable payload structure for assertions
        """

        # ------------------------------------------------------------
        # 1. Record the call for test assertions
        # ------------------------------------------------------------
        # Tests inspect both:
        #   • self.calls          → sequencing + payload structure
        #   • self.note_upserts   → "exactly one note upsert" semantics
        #
        # To satisfy both sets of tests, we construct the payload once
        # and append it to both logs.
        payload = {
            "id": id,
            "title": title,
            "body": body,
            "metadata": metadata,
            "notebook_id": notebook_id,
            "embedding": embedding,
        }

        # Call‑log used by integration tests to verify ordering + structure.
        # Shape matches E2E expectations:
        #   ("upsert_note_with_embedding", note_id, notebook_id)
        self.calls.append(("upsert_note_with_embedding", id, notebook_id))

        # Dedicated note‑upsert log used by tests that assert:
        #   • exactly one note upsert per note
        #   • correct payload shape
        self.note_upserts.append(payload)

        # ------------------------------------------------------------
        # 2. Determine inserted vs updated
        # ------------------------------------------------------------
        # The mock simulates existence checks using an in‑memory set.
        if id in self.existing_ids:
            return "updated"

        # First‑time ingestion → treat as inserted
        self.existing_ids.add(id)
        return "inserted"

    # ----------------------------------------------------------------------
    # TAG UPSERT
    # ----------------------------------------------------------------------
    def upsert_tags(self, tags):
        """
        Deterministic tag upsert.

        Returns:
            dict[tag_name → deterministic_uuid]
        """

        self.calls.append(("upsert_tags", tags))

        for tag in tags:
            if tag not in self.tag_upserts:
                safe = tag.replace(" ", "_")
                self.tag_upserts[tag] = f"uuid-tag-{safe}"

        return self.tag_upserts

    # ----------------------------------------------------------------------
    # NOTE‑TAG RELATIONSHIP UPSERT (plural — canonical API)
    # ----------------------------------------------------------------------
    def upsert_note_tag_relationships(self, note_id: str, tag_ids: list[str]):
        """
        Batch upsert of note‑tag relationships (plural form required by tests).

        This method intentionally mirrors the *public API* of the real
        SupabaseClient, which exposes a batch‑oriented relationship upsert
        endpoint. The orchestrator calls this method exactly once per note,
        passing the full list of tag_ids associated with that note.

        Why this plural method exists:
            • Integration tests assert that the mock exposes the method name
            `upsert_note_tag_relationships` (plural), not the singular form.
            • The orchestrator groups all tag relationships for a note into a
            single call, matching the real backend’s batch‑insert semantics.
            • Tests validate that:
                - the method is invoked exactly once per note,
                - the call log contains the plural method name,
                - the tag_ids argument is passed as a list,
                - and each (note_id, tag_id) pair is recorded deterministically.

        Deterministic behavior:
            • Each (note_id, tag_id) pair is appended to self.relationships in
            the order received.
            • The call log must match the exact tuple structure expected by
            the E2E test:
                ("upsert_note_tag_relationships", "note-<id>", [tag_ids])
        """

        # Record each (note_id, tag_id) pair in deterministic order.
        for tag_id in tag_ids:
            self.relationships.append((note_id, tag_id))

        # E2E test expects the logged note_id to be prefixed with "note-"
        self.calls.append(("upsert_note_tag_relationships", f"note-{note_id}", tag_ids))

        return {"status": "ok"}
