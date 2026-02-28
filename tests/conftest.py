"""
Shared pytest configuration for the Milestone 8.8 test suite.

This file centralizes all reusable testing utilities so that:
    • Integration tests use deterministic mock clients
    • Parsed note fixtures load consistently
    • Embedding + Supabase mocks behave predictably
    • Tests remain contributor‑friendly and easy to extend

All helpers here are intentionally simple and deterministic to ensure
stable test behavior across environments and future refactors.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

# ============================================================================
# FIXTURE DIRECTORY
# ============================================================================
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ============================================================================
# 1.1 — SHARED TEST INFRASTRUCTURE
# ============================================================================


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provides a fresh Typer CliRunner instance for CLI tests."""
    return CliRunner()


@pytest.fixture
def load_json_fixture():
    """Load a JSON fixture from tests/fixtures/ as a Python dict."""

    def _loader(name: str) -> dict:
        path = FIXTURES_DIR / name
        text = path.read_text(encoding="utf-8")
        return json.loads(text)

    return _loader


@pytest.fixture
def load_text_fixture():
    """Load a raw text fixture from tests/fixtures/."""

    def _loader(name: str) -> str:
        path = FIXTURES_DIR / name
        return path.read_text(encoding="utf-8")

    return _loader


# ============================================================================
# 1.2 — DETERMINISTIC MOCK CLIENTS + UTILITY FIXTURES
# ============================================================================


# ---------------------------------------------------------------------------
# Fixture: mock_embedding_client
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_embedding_client():
    """
    Deterministic embedding client for integration tests.

    Exposes:
        • .generate(text) → [1.0, 2.0, 3.0]
        • .calls → number of times generate() was invoked
    """

    class MockEmbeddingClient:
        def __init__(self):
            self.calls = 0

        def generate(self, text: str):
            self.calls += 1
            return [1.0, 2.0, 3.0]

    return MockEmbeddingClient()


# ---------------------------------------------------------------------------
# Fixture: mock_supabase_client
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_supabase_client(mock_embedding_client):
    """
    Deterministic Supabase client mock for integration tests.

    Mirrors the real SupabaseClient interface:

        • upsert_note_with_embedding(...)
        • upsert_notebooks(...)
        • upsert_tags(...)
        • upsert_note_tag_relationships(...)

    IMPORTANT:
        This mock is intentionally *append‑only*. Real Supabase upserts
        are idempotent, but this mock records every call so integration
        tests can assert that the orchestrator produces identical writes
        across multiple runs.

    Tracks all upserts separately so integration tests can assert:
        • correct payload structure
        • correct number of writes
        • idempotency behavior
    """

    class MockSupabaseClient:
        def __init__(self):
            # Track all upsert types
            self.note_upserts = []
            self.notebook_upserts = []
            self.tag_upserts = []
            self.relationship_upserts = []

            # Embedding client injected for deterministic behavior
            self.embedding_client = mock_embedding_client

        # --------------------------------------------------------------
        # 1.2.1 — NOTE UPSERTS (WITH EMBEDDINGS)
        # --------------------------------------------------------------
        def upsert_note_with_embedding(
            self,
            *,
            id,
            title,
            body,
            metadata,
            notebook_id,
            embedding,  # ← ADDED: orchestrator always passes this
        ):
            """
            Mirrors the real SupabaseClient API.

            The orchestrator ALWAYS calls this method using keyword
            arguments, so the mock must accept keyword parameters.

            The mock:
                • accepts the precomputed embedding from the orchestrator
                • builds a payload identical to the real client
                • stores it for test assertions
            """

            payload = {
                "id": id,
                "title": title,
                "body": body,
                "metadata": metadata,
                "notebook_id": notebook_id,
                "embedding": embedding,  # ← store the embedding exactly as passed
            }

            self.note_upserts.append(payload)

            # Integration tests expect Option B1 semantics ("inserted" / "updated").
            # For deterministic behavior, treat all writes as "inserted".
            return "inserted"

        # --------------------------------------------------------------
        # NOTEBOOK UPSERT (plural)
        # --------------------------------------------------------------
        def upsert_notebooks(self, notebook_map: dict):
            """
            The orchestrator expects a mapping:
                { notebook_name: notebook_id }

            The mock returns a deterministic mapping and stores each
            notebook upsert for assertions.
            """
            result = {}

            for name, metadata in notebook_map.items():
                notebook_id = f"notebook-{name.lower().replace(' ', '-')}"
                result[name] = notebook_id

                self.notebook_upserts.append(
                    {
                        "name": name,
                        "metadata": metadata,
                        "id": notebook_id,
                    }
                )

            return result

        # --------------------------------------------------------------
        # TAG UPSERT (plural)
        # --------------------------------------------------------------
        def upsert_tags(self, tag_map: dict):
            """
            The orchestrator expects a mapping:
                { tag_name: tag_id }

            The mock:
                • generates deterministic tag IDs
                • stores each tag upsert as a dict
                • returns the same mapping structure as the real client
            """
            result = {}

            for tag_name in tag_map:
                tag_id = f"tag-{tag_name.lower().replace(' ', '-')}"
                result[tag_name] = tag_id

                self.tag_upserts.append(
                    {
                        "name": tag_name,
                        "id": tag_id,
                    }
                )

            return result

        # --------------------------------------------------------------
        # NOTE–TAG RELATIONSHIP UPSERTS
        # --------------------------------------------------------------
        def upsert_note_tag_relationships(self, note_id, tag_ids):
            """
            Mirrors the real SupabaseClient API:

                upsert_note_tag_relationships(note_id, tag_ids)

            The mock:
                • creates one relationship per tag
                • stores each relationship deterministically
            """
            for tag_id in tag_ids:
                rel = {
                    "note_id": note_id,
                    "tag_id": tag_id,
                }
                self.relationship_upserts.append(rel)

            return {"status": "ok"}

    return MockSupabaseClient()


# ---------------------------------------------------------------------------
# Fixture: temp_work_dir
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_work_dir(tmp_path):
    """Provides a temporary working directory for tests."""
    return tmp_path
