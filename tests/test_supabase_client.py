"""
Unit tests for SupabaseClient using the deterministic DummyClient.

These tests verify:
    - correct construction of UpsertNoteRecord,
    - embedding generation,
    - deterministic embedding behavior,
    - and proper error handling.

Run from project root:
    pytest -q
"""

from typing import List

import pytest

from pke.supabase_client import SupabaseClient, compute_embedding
from pke.types import UpsertNoteRecord
from tests.dummy_supabase import DummyClient  # Fully typed, reusable test double


# =====================================================================
# Test: Successful upsert
# =====================================================================


def test_upsert_note_with_embedding_returns_record_and_embedding_length() -> None:
    """
    Verifies that SupabaseClient.upsert_note_with_embedding:

      • returns a list with one record
      • preserves title, body, and metadata fields
      • attaches a 1536‑dimensional embedding vector

    The returned record is an UpsertNoteRecord, not a NoteRecord.
    """
    client = SupabaseClient(client=DummyClient())

    title = "Unit Test"
    body = "unit test body"
    metadata = {"test": True}

    # ✅ Correct type: UpsertNoteRecord, not NoteRecord
    res: List[UpsertNoteRecord] = client.upsert_note_with_embedding(
        title=title,
        body=body,
        metadata=metadata,
    )

    # Validate structure
    assert isinstance(res, list)
    assert len(res) == 1

    rec = res[0]

    # ✅ UpsertNoteRecord fields
    assert rec["title"] == title
    assert rec["body"] == body
    assert rec["metadata"] == metadata

    # ✅ Embedding must exist and be 1536‑dimensional
    emb = rec.get("embedding")
    assert emb is not None
    assert isinstance(emb, list)
    assert len(emb) == 1536


# =====================================================================
# Test: Embedding determinism
# =====================================================================


def test_compute_embedding_is_deterministic() -> None:
    """
    Ensures the local embedding stub is deterministic:

      • same input → identical vectors
      • different input → different vectors
    """
    a = compute_embedding("same text")
    b = compute_embedding("same text")
    c = compute_embedding("different text")

    assert a == b, "compute_embedding should be deterministic for identical input"
    assert a != c, "different inputs should produce different embeddings"


# =====================================================================
# Test: Error handling
# =====================================================================


def test_upsert_note_with_embedding_raises_on_empty_body() -> None:
    """
    Ensures that calling upsert_note_with_embedding with an empty body
    raises ValueError.
    """
    client = SupabaseClient(client=DummyClient())

    with pytest.raises(ValueError, match="body must be provided"):
        client.upsert_note_with_embedding(title="Missing Body", body="")


def test_upsert_note_with_embedding_raises_if_client_is_none() -> None:
    """
    Ensures that calling upsert_note_with_embedding without a client
    raises RuntimeError.
    """
    client = SupabaseClient(client=None)

    with pytest.raises(RuntimeError, match="No client provided to SupabaseClient"):
        client.upsert_note_with_embedding(title="No Client", body="test body")
