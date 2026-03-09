"""
pke/embedding/openai_client.py

This module implements the EmbeddingClient protocol using OpenAI's
text-embedding-3-small model.

WHY: To provide real semantic embeddings for the ingestion pipeline,
replacing the deterministic stub. This enables accurate retrieval and
insight generation in the PKE system by leveraging OpenAI's high-quality
embedding model.
"""

import openai
import tiktoken
from pke.embedding.embedding_client import EmbeddingClient


class OpenAIEmbeddingError(Exception):
    """
    Raised when the OpenAI embedding API call fails for any reason.

    WHY: Provides a typed exception for embedding failures, allowing
    callers to handle API errors explicitly without swallowing them.
    """

    pass


class OpenAIEmbeddingClient(EmbeddingClient):
    """
    EmbeddingClient implementation backed by OpenAI text-embedding-3-small.

    WHY: Injects API key and model name via constructor for testability.
    Provides real embeddings for production use in the ingestion pipeline.
    """

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        # ----------------------------------------------------------------------
        # ⭐ 1. Initialize OpenAI client
        #
        # WHY: Set up the OpenAI client with the provided API key for making
        # embedding requests. The model is configurable but defaults to
        # text-embedding-3-small for consistency with PKE requirements.
        # ----------------------------------------------------------------------
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def embed(self, text: str) -> list[float]:
        # ----------------------------------------------------------------------
        # ⭐ 2. Generate embedding via OpenAI API
        #
        # WHY: Call the OpenAI embeddings endpoint to get the semantic vector
        # representation of the input text. Truncates to 32000 characters
        # (~8000 tokens) to stay within OpenAI's 8192 token limit.
        # Note-level embeddings on long notes are fallback only — these notes
        # are always retrieved via chunk embeddings anyway.
        # ----------------------------------------------------------------------
        try:
            encoder = tiktoken.encoding_for_model("text-embedding-3-small")
            tokens = encoder.encode(text)
            if len(tokens) > 8191:
                tokens = tokens[:8191]
                text = encoder.decode(tokens)
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            raise OpenAIEmbeddingError(f"OpenAI embedding failed: {e}") from e

    def generate(self, text: str) -> list[float]:
        """
        Backwards-compatible alias for embed().

        WHY: The orchestrator calls .generate() on the embedding client.
        This alias ensures OpenAIEmbeddingClient satisfies that contract
        without requiring changes to the orchestrator.
        """
        return self.embed(text)
