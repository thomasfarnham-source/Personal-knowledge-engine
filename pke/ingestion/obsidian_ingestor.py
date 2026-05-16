from dataclasses import dataclass
from typing import Any

from pke.chunking.chunker import chunk_note
from pke.embedding.embedding_client import EmbeddingClient
from pke.parsers.obsidian_parser import ParsedNote
from pke.supabase_client import SupabaseClient


@dataclass
class ObsidianIngestResult:
    notes_processed: int
    chunks_written: int
    errors: list[str]


def ingest_obsidian_notes(
    notes: list[ParsedNote],
    supabase_client: SupabaseClient,
    embedding_client: EmbeddingClient,
    dry_run: bool = False,
) -> ObsidianIngestResult:
    """
    Ingest parsed Obsidian notes into retrieval_units.

    Strategy:
    - Parser emits one ParsedNote per file.
    - Ingestor chunks note text and writes one retrieval_units row per chunk.
    - Notes below threshold write one whole-note fallback retrieval_units row.
    - Re-ingest uses delete-and-rewrite semantics.
    """
    result = ObsidianIngestResult(notes_processed=0, chunks_written=0, errors=[])

    for note in notes:
        result.notes_processed += 1

        chunks = chunk_note(
            body=note.body,
            created_at=note.created_at,
            title=note.title,
            notebook=note.notebook,
        )

        rows: list[dict[str, Any]] = []

        if chunks:
            for chunk in chunks:
                source_id = f"{note.id}::chunk::{chunk.chunk_index}"
                row_metadata = dict(note.metadata or {})
                row_metadata.update(
                    {
                        "chunk_index": chunk.chunk_index,
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,
                        "section_title": chunk.section_title,
                        "entry_timestamp": chunk.entry_timestamp,
                        "resource_ids": chunk.resource_ids,
                        "chunk_metadata": chunk.metadata,
                    }
                )

                if dry_run:
                    embedding = None
                else:
                    try:
                        embedding = embedding_client.generate(chunk.chunk_text)
                    except ValueError as exc:
                        result.errors.append(
                            f"note_id={note.id} chunk_index={chunk.chunk_index} "
                            f"embedding_error: {exc}"
                        )
                        continue

                rows.append(
                    {
                        "source_type": "obsidian",
                        "source_id": source_id,
                        "body": chunk.chunk_text,
                        "embedding": embedding,
                        "title": note.title or None,
                        "notebook": note.notebook or None,
                        "created_at": note.created_at or None,
                        "updated_at": note.updated_at or None,
                        "participants": note.participants,
                        "privacy_tier": note.privacy_tier or 2,
                        "dominant_sender": note.dominant_sender,
                        "thread_id": note.thread_id,
                        "thread_type": note.thread_type,
                        "metadata": row_metadata,
                    }
                )
        else:
            row_metadata = dict(note.metadata or {})
            row_metadata["chunk_fallback"] = True

            if dry_run:
                embedding = None
            else:
                try:
                    embedding = embedding_client.generate(note.body)
                except ValueError as exc:
                    result.errors.append(f"note_id={note.id} chunk_index=0 embedding_error: {exc}")
                    continue

            rows.append(
                {
                    "source_type": "obsidian",
                    "source_id": note.id,
                    "body": note.body,
                    "embedding": embedding,
                    "title": note.title or None,
                    "notebook": note.notebook or None,
                    "created_at": note.created_at or None,
                    "updated_at": note.updated_at or None,
                    "participants": note.participants,
                    "privacy_tier": note.privacy_tier or 2,
                    "dominant_sender": note.dominant_sender,
                    "thread_id": note.thread_id,
                    "thread_type": note.thread_type,
                    "metadata": row_metadata,
                }
            )

        result.chunks_written += len(rows)

        if dry_run or not rows:
            continue

        try:
            # Non-transactional v1 assumption: failure during delete-and-rewrite can leave
            # temporary inconsistency until the next ingestion run.
            _delete_existing_rows_for_note(note_id=note.id, supabase_client=supabase_client)
            supabase_client.upsert_rows("retrieval_units", rows)
        except RuntimeError as exc:
            result.errors.append(f"note_id={note.id} chunk_index=n/a write_error: {exc}")

    return result


def _delete_existing_rows_for_note(note_id: str, supabase_client: SupabaseClient) -> None:
    """
    Delete fallback and chunk rows for one Obsidian note in one round-trip.
    """
    client = supabase_client.client
    if client is None:
        raise RuntimeError("Supabase client is not configured for deletion.")

    delete_filter = f"source_id.eq.{note_id},source_id.like.{note_id}::chunk::%"
    response = (
        client.table("retrieval_units")
        .delete()
        .eq("source_type", "obsidian")
        .or_(delete_filter)
        .execute()
    )

    # Supabase wrappers in this repo may return dict-style or SDK-style responses;
    # handle both to surface errors consistently.
    if isinstance(response, dict) and response.get("status", 200) >= 400:
        raise RuntimeError(f"Supabase error during delete-and-rewrite: {response}")

    error = getattr(response, "error", None)
    if error:
        raise RuntimeError(f"Supabase error during delete-and-rewrite: {error}")
