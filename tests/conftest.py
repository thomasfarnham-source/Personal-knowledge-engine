"""
Shared pytest configuration for the Milestone 8.8 test suite.

This file centralizes all reusable testing utilities so that:
    • CLI tests receive a fresh, isolated Typer CliRunner
    • Unit and integration tests can load deterministic fixtures
    • Mock embedding and Supabase clients behave predictably
    • Tests remain contributor‑friendly, explicit, and easy to extend

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
# All test fixtures live under tests/fixtures/. Using a fixed, explicit path
# ensures deterministic loading and avoids ambiguity about where test data
# should be placed.
# ============================================================================
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ============================================================================
# 1.1 — SHARED TEST INFRASTRUCTURE
# ============================================================================


# ---------------------------------------------------------------------------
# Fixture: cli_runner
#
# Provides a fresh Typer CliRunner instance for each test. This simulates
# command‑line execution in an isolated environment without spawning a real
# subprocess. Tests can invoke the CLI exactly as a user would:
#
#     result = cli_runner.invoke(app, ["notes", "upsert", "file.json"])
#
# Each test receives a clean runner to prevent shared state or output
# contamination between tests.
# ---------------------------------------------------------------------------
@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Fixture: load_json_fixture
#
# Loads a JSON fixture from tests/fixtures/ and returns it as a Python dict.
#
# Usage:
#     note = load_json_fixture("note_simple.json")
#
# This keeps fixture loading consistent and avoids repeating boilerplate
# path logic across multiple test files.
# ---------------------------------------------------------------------------
@pytest.fixture
def load_json_fixture():
    def _loader(name: str) -> dict:
        path = FIXTURES_DIR / name
        text = path.read_text(encoding="utf-8")
        return json.loads(text)

    return _loader


# ---------------------------------------------------------------------------
# Fixture: load_text_fixture
#
# Some tests (especially CLI tests) may need to load raw text files rather
# than JSON. This helper mirrors load_json_fixture but returns plain text.
#
# Usage:
#     content = load_text_fixture("example.md")
# ---------------------------------------------------------------------------
@pytest.fixture
def load_text_fixture():
    def _loader(name: str) -> str:
        path = FIXTURES_DIR / name
        return path.read_text(encoding="utf-8")

    return _loader


# ============================================================================
# 1.2 — DETERMINISTIC MOCK CLIENTS + UTILITY FIXTURES
# ============================================================================


# ---------------------------------------------------------------------------
# Fixture: mock_embedding_client
#
# Provides a deterministic embedding client for integration tests.
# This avoids calling the real embedding provider and ensures stable,
# reproducible embeddings for every test run.
#
# The returned object exposes a .generate(text) method that mimics the
# real client but always returns the same predictable vector.
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_embedding_client():
    class MockEmbeddingClient:
        def generate(self, text: str):
            # Deterministic fake embedding (length 3 for simplicity)
            return [1.0, 2.0, 3.0]

    return MockEmbeddingClient()


# ---------------------------------------------------------------------------
# Fixture: mock_supabase_client
#
# Provides a deterministic Supabase client mock for integration tests.
# It records all upsert calls so tests can assert:
#     • number of writes
#     • payload structure
#     • idempotency behavior
#
# The real Supabase client returns structured responses; this mock returns
# a minimal, predictable dict suitable for assertions.
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_supabase_client():
    class MockSupabaseClient:
        def __init__(self):
            self.upserts = []

        def upsert(self, payload: dict):
            self.upserts.append(payload)
            return {"status": "ok", "count": len(self.upserts)}

    return MockSupabaseClient()


# ---------------------------------------------------------------------------
# Fixture: temp_work_dir
#
# Provides a temporary working directory for tests that need to write files.
# This keeps the real project directory clean and ensures isolation.
#
# pytest's built‑in tmp_path fixture supplies a unique directory per test.
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_work_dir(tmp_path):
    return tmp_path
