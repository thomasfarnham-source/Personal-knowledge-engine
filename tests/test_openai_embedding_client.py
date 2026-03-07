"""
Unit tests for OpenAIEmbeddingClient.

All OpenAI API calls are mocked — no real network calls are made.

These tests validate:
    • correct embedding dimensions (1536 floats)
    • proper error handling (OpenAIEmbeddingError raised on API failure)
    • correct model name passed to the API
    • backwards-compatible generate() alias for embed()

Run from project root:
    pytest -q tests/test_openai_embedding_client.py
"""

from unittest.mock import MagicMock, patch

import pytest

from pke.embedding.openai_client import (
    OpenAIEmbeddingClient,
    OpenAIEmbeddingError,
)


# =========================================================================
# Test 1: Embedding returns correct dimension
# =========================================================================
def test_embed_returns_correct_dimension() -> None:
    """
    Validates that embed() returns a list of exactly 1536 floats.

    WHY: OpenAI text-embedding-3-small always returns 1536-dimensional
    vectors. This test ensures the client correctly unwraps the API
    response and returns the embedding as a list.
    """
    # Mock embedding data: 1536 floats
    mock_embedding = [1.0] * 1536

    # Mock the OpenAI client
    with patch("pke.embedding.openai_client.openai.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Configure the mock to return a response with the embedding
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_client.embeddings.create.return_value = mock_response

        # Create the real OpenAIEmbeddingClient with mocked OpenAI
        client = OpenAIEmbeddingClient(api_key="test-key")

        # Call embed()
        result = client.embed("test text")

        # Assert
        assert isinstance(result, list)
        assert len(result) == 1536
        assert all(isinstance(x, float) for x in result)


# =========================================================================
# Test 2: API failure raises typed exception
# =========================================================================
def test_embed_raises_on_api_failure() -> None:
    """
    Validates that embed() raises OpenAIEmbeddingError (not generic
    Exception) when the OpenAI API fails.

    WHY: Typed exceptions allow calling code to handle embedding
    failures explicitly without swallowing other exceptions.
    """
    with patch("pke.embedding.openai_client.openai.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Configure the mock to raise an exception
        mock_client.embeddings.create.side_effect = Exception("API rate limit")

        client = OpenAIEmbeddingClient(api_key="test-key")

        # Assert that OpenAIEmbeddingError is raised (not a generic Exception)
        with pytest.raises(OpenAIEmbeddingError) as exc_info:
            client.embed("test text")

        # Verify the original exception is chained
        assert exc_info.value.__cause__ is not None
        assert "API rate limit" in str(exc_info.value.__cause__)


# =========================================================================
# Test 3: Correct model name passed to API
# =========================================================================
def test_embed_sends_correct_model() -> None:
    """
    Validates that embed() passes the correct model name
    ("text-embedding-3-small") to the OpenAI API.

    WHY: The model name is critical for reproducibility. Swapping
    models would break existing embeddings.
    """
    mock_embedding = [1.0] * 1536

    with patch("pke.embedding.openai_client.openai.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_client.embeddings.create.return_value = mock_response

        client = OpenAIEmbeddingClient(api_key="test-key")
        client.embed("test text")

        # Assert the model was passed correctly
        mock_client.embeddings.create.assert_called_once()
        call_kwargs = mock_client.embeddings.create.call_args.kwargs
        assert call_kwargs["model"] == "text-embedding-3-small"


# =========================================================================
# Test 4: generate() aliases embed() correctly
# =========================================================================
def test_generate_aliases_embed() -> None:
    """
    Validates that generate() is a backwards-compatible alias for embed().

    WHY: The orchestrator calls .generate() on the embedding client.
    This alias ensures OpenAIEmbeddingClient works without orchestrator
    changes.
    """
    mock_embedding = [2.0] * 1536

    with patch("pke.embedding.openai_client.openai.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_client.embeddings.create.return_value = mock_response

        client = OpenAIEmbeddingClient(api_key="test-key")

        # Call generate()
        result_generate = client.generate("test text")

        # Reset the mock to isolate the embed() call
        mock_client.embeddings.create.reset_mock()
        mock_client.embeddings.create.return_value = mock_response

        # Call embed() with the same text
        result_embed = client.embed("test text")

        # Assert both return identical embeddings
        assert result_generate == result_embed
        assert result_generate == mock_embedding
