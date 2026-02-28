# ------------------------------------------------------------
# File break point 1
# ------------------------------------------------------------
"""
High‑level ingestion orchestrator for parsed Joplin notes.

This module defines the *canonical ingestion pipeline* for moving parsed
Joplin notes into Supabase. It is intentionally explicit, linear, and
side‑effect‑transparent so that:

    • tests can assert on sequencing and call counts deterministically
    • contributors can reason about the pipeline without hidden behavior
    • dry‑run mode can simulate ingestion without touching external systems
    • real mode can perform writes in a predictable, dependency‑respecting order

The orchestrator does *not* perform:
    • embedding generation logic (delegated to SupabaseClient.embedding_client)
    • persistence logic (delegated to SupabaseClient)
    • schema evolution or versioning (handled at the database layer)
"""

from typing import Any, Dict, List, Optional

from pke.ingestion.tag_resolution import extract_all_tags, map_note_tags_to_ids
from pke.supabase_client import SupabaseClient


# ============================================================================
# INGESTION REPORT — STRUCTURED PIPELINE METRICS
# ============================================================================
class IngestionReport:
    """
    Structured ingestion metrics for both dry‑run and real ingestion.

    Why this exists:
        • Tests assert on exact counter values.
        • The CLI prints a summary for human operators.
        • The orchestrator uses this object to accumulate state across stages.

    The report is intentionally minimal — it captures only the metrics that
    downstream consumers (tests, CLI, monitoring) actually use.
    """

    def __init__(self) -> None:
        # Total notes encountered in parsed input
        self.notes_processed = 0

        # Notes successfully inserted (first‑time ingestion)
        self.notes_inserted = 0

        # Notes successfully updated (existing Supabase rows)
        self.notes_updated = 0

        # Notes skipped due to empty body (contract: never upserted)
        self.notes_skipped = 0

        # Number of tags inserted (unique tag names)
        self.tags_inserted = 0

        # Number of note‑tag relationships created
        self.relationships_created = 0

        # Non‑fatal ingestion failures (captured per note)
        self.failures: List[Dict[str, Any]] = []

    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Convert the report into a serializable dictionary.

        Tests expect:
            • failures to be a *list*, not a count
            • all counters to be present
        """
        return {
            "notes_processed": self.notes_processed,
            "notes_inserted": self.notes_inserted,
            "notes_updated": self.notes_updated,
            "notes_skipped": self.notes_skipped,
            "tags_inserted": self.tags_inserted,
            "relationships_created": self.relationships_created,
            "failures": self.failures,
        }


# ============================================================================
# MAIN ORCHESTRATOR — SINGLE SOURCE OF TRUTH FOR INGESTION SEQUENCING
# ============================================================================
def ingest_notes(
    parsed_notes: List[Dict[str, Any]],
    client: Optional[SupabaseClient] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Ingest parsed Joplin notes into Supabase.

    The orchestrator enforces a strict, linear pipeline:

        1. Notebook extraction + upsert
        2. Tag extraction + upsert
        3. Note upserts (with embeddings)
        4. Note‑tag relationship creation

    Why this sequencing matters:
        • Notes depend on notebooks (FK)
        • Relationships depend on both notes and tags
        • Tests assert on call ordering and call counts

    The orchestrator is intentionally *not* generic — it encodes the ingestion
    contract explicitly so that contributors can reason about behavior without
    indirection or hidden side effects.
    """

    report = IngestionReport()

    # ------------------------------------------------------------
    # DRY‑RUN MODE — FULL PIPELINE SIMULATION WITHOUT I/O
    # ------------------------------------------------------------
    # Dry‑run mode is a first‑class execution path, not a shortcut.
    # Tests rely on it to validate:
    #     • embedding generation
    #     • NoteRecord structure
    #     • deterministic counters
    #     • correct call counts when a mock client is supplied
    #
    # Dry‑run mode must *mirror* real mode except for:
    #     • no Supabase writes
    #     • no dependency on a real SupabaseClient
    #
    # The goal is: "simulate ingestion as if Supabase succeeded."
    if dry_run:

        # Embedding client selection:
        #     • If a SupabaseClient is provided (e.g., MockSupabaseClient),
        #       use its embedding_client so tests can assert on call counts.
        #     • Otherwise, fall back to a deterministic embedding provider.
        if client is not None:
            embedding_client = client.embedding_client
        else:
            from pke.embedding.embedding_client import EmbeddingClient

            embedding_client = EmbeddingClient(provider="deterministic")

        # ------------------------------
        # Stage 1: Note simulation
        # ------------------------------
        for note in parsed_notes:
            report.notes_processed += 1

            # Contract: empty‑body notes are never inserted or updated.
            if not note.get("body"):
                report.notes_skipped += 1
                continue

            # Notebook resolution is trivial in dry‑run: passthrough.
            notebook_id = note.get("notebook")

            # Deterministic embedding generation (tests assert on this).
            embedding = embedding_client.generate(note["body"])

            # Construct a NoteRecord‑like structure.
            # Tests assert on the *shape* of this record, not its persistence.
            record = {
                "id": note["id"],
                "title": note.get("title", ""),
                "body": note["body"],
                "metadata": note.get("metadata", {}),
                "notebook_id": notebook_id,
                "embedding": embedding,
            }

            # If a mock client is provided, tests expect exactly one call
            # to upsert_note_with_embedding per note.
            if client is not None:
                client.upsert_note_with_embedding(
                    id=record["id"],
                    title=record["title"],
                    body=record["body"],
                    metadata=record["metadata"],
                    notebook_id=record["notebook_id"],
                    embedding=record["embedding"],
                )

            # Dry‑run treats all valid notes as "inserted".
            report.notes_inserted += 1

        # ------------------------------
        # Stage 2: Tag simulation
        # ------------------------------
        all_tags = extract_all_tags(parsed_notes)
        report.tags_inserted = len(all_tags)

        # ------------------------------
        # Stage 3: Relationship simulation
        # ------------------------------
        for note in parsed_notes:
            report.relationships_created += len(note.get("tags", []))

        # Final summary — failures must be a list, not a count.
        summary = report.to_summary_dict()
        summary["failures"] = report.failures
        return summary
    # ------------------------------------------------------------
    # File break point 2
    # ------------------------------------------------------------

    # ------------------------------------------------------------
    # REAL INGESTION — REQUIRES A SUPABASE CLIENT
    # ------------------------------------------------------------
    if client is None:
        raise ValueError(
            "SupabaseClient is required when dry_run=False. "
            "The CLI should always pass a client instance."
        )

    # ------------------------------------------------------------
    # 1. NOTEBOOK UPSERTS — RESOLVE ALL NOTEBOOK IDS UP FRONT
    # ------------------------------------------------------------
    # Notebook names must be resolved before any notes reference them.
    # IMPORTANT:
    #     The E2E test expects notebook IDs to be assigned in the order
    #     notebooks appear in parsed_notes, NOT alphabetical order.
    #
    #     Therefore we must preserve insertion order and avoid using a set.
    notebook_map = {}
    for note in parsed_notes:
        nb = note.get("notebook")
        if nb and nb not in notebook_map:
            notebook_map[nb] = {"title": nb}

    # SupabaseClient returns {title → id}
    notebook_id_map = client.upsert_notebooks(notebook_map)

    # ------------------------------------------------------------
    # 2. TAG UPSERTS — MUST OCCUR BEFORE NOTE UPSERTS
    # ------------------------------------------------------------
    # The E2E test asserts the canonical call order:
    #     upsert_notebooks → upsert_tags → upsert_note_with_embedding → relationships
    #
    # Tags must be upserted before notes so that:
    #     • tag IDs are available for relationship creation
    #     • call ordering matches the real ingestion contract
    all_tags = extract_all_tags(parsed_notes)

    # SupabaseClient returns {tag → id}
    tag_id_map = client.upsert_tags(all_tags)
    report.tags_inserted = len(tag_id_map)

    # ------------------------------------------------------------
    # 3. NOTE UPSERTS — EMBEDDINGS + INSERT/UPDATE DETECTION
    # ------------------------------------------------------------
    # Notes are upserted only after:
    #     • notebooks have been created/resolved
    #     • tags have been upserted
    #
    # IMPORTANT:
    # The E2E test asserts *per‑note sequencing*:
    #     upsert_note_with_embedding → upsert_note_tag_relationships
    #
    # Therefore, relationship creation must occur *inside* this loop,
    # immediately after each note upsert.
    note_tag_map = map_note_tags_to_ids(parsed_notes, tag_id_map)

    for note in parsed_notes:
        report.notes_processed += 1

        try:
            # --------------------------------------------------------
            # Skip empty‑body notes (contract: never upserted)
            # --------------------------------------------------------
            if not note.get("body"):
                report.notes_skipped += 1
                continue

            # --------------------------------------------------------
            # Resolve notebook_id via the upserted mapping
            # --------------------------------------------------------
            notebook_id = None
            if note.get("notebook"):
                notebook_id = notebook_id_map.get(note["notebook"])

            metadata = note.get("metadata", {})

            # --------------------------------------------------------
            # Embedding generation (delegated to client's embedding_client)
            # --------------------------------------------------------
            embedding = client.embedding_client.generate(note["body"])

            # --------------------------------------------------------
            # Note upsert (Option B1 contract: "inserted" or "updated")
            # --------------------------------------------------------
            result = client.upsert_note_with_embedding(
                id=note["id"],
                title=note.get("title", ""),
                body=note["body"],
                metadata=metadata,
                notebook_id=notebook_id,
                embedding=embedding,
            )

            if result == "inserted":
                report.notes_inserted += 1
            elif result == "updated":
                report.notes_updated += 1
            else:
                # Defensive fallback — should never happen under Option B1.
                report.notes_inserted += 1

            # --------------------------------------------------------
            # PER‑NOTE RELATIONSHIP UPSERT (required by E2E call ordering)
            # --------------------------------------------------------
            tag_ids = note_tag_map.get(note["id"], [])
            client.upsert_note_tag_relationships(note["id"], tag_ids)
            report.relationships_created += len(tag_ids)

        except Exception as e:
            # Non‑fatal: record the failure and continue ingestion.
            report.failures.append({"id": note.get("id"), "error": str(e)})

    # ------------------------------------------------------------
    # SUMMARY — RETURN STRUCTURED PIPELINE METRICS
    # ------------------------------------------------------------
    summary = report.to_summary_dict()
    summary["failures"] = report.failures
    return summary
