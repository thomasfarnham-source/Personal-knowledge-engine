# tests/test_supabase_client.py
# Unit tests for supabase_client.SupabaseClient using a deterministic embedding stub.
#
# Run from project root:
#   pytest -q

import sys
import pathlib
import pytest

# Ensure the project root is on sys.path so we can import modules directly
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

from supabase_client import SupabaseClient, compute_embedding
from tests.dummy_supabase import DummyClient  # Typed, reusable test double


# -------------------------
# Test: Upsert behavior
# -------------------------

def test_upsert_note_with_embedding_returns_record_and_embedding_length():
    """
    Verifies that SupabaseClient.upsert_note_with_embedding:
      - returns a list with one record,
      - preserves title, body, and metadata fields,
      - attaches a 1536-dimensional embedding vector.
    """
    # Inject the dummy client to avoid real network calls
    client = SupabaseClient(client=DummyClient())

    # Define test input
    title = "Unit Test"
    body = "unit test body"
    metadata = {"test": True}

    # Call the method under test
    res = client.upsert_note_with_embedding(title=title, body=body, metadata=metadata)

    # Validate response structure
    assert isinstance(res, list), "response should be a list"
    assert len(res) == 1, "response should contain exactly one record"

    rec = res[0]
    assert rec["title"] == title
    assert rec["body"] == body
    assert rec["metadata"] == metadata

    # Validate embedding
    emb = rec.get("embedding")
    assert emb is not None, "embedding must be present in the record"
    assert isinstance(emb, list), "embedding must be a list"
    assert len(emb) == 1536, "embedding must be 1536-dimensional"


# -------------------------
# Test: Embedding determinism
# -------------------------

def test_compute_embedding_is_deterministic():
    """
    Ensures the local embedding stub is deterministic:
      - same input => identical vectors
      - different input => different vectors
    """
    a = compute_embedding("same text")
    b = compute_embedding("same text")
    c = compute_embedding("different text")

    assert a == b, "compute_embedding should be deterministic for identical input"
    assert a != c, "different inputs should produce different embeddings"
