"""
EmbeddingClient abstraction layer.

This module defines the EmbeddingClient class, which provides a unified
interface for generating embeddings regardless of the underlying provider.

Today, EmbeddingClient delegates to the deterministic stub implementation
in `deterministic.py`. In future milestones, this class will be extended
to support multiple providers, such as:

    • OpenAI
        Industry‑standard semantic embeddings with strong performance on
        retrieval‑augmented generation (RAG) tasks. The OpenAI provider
        will wrap the `/embeddings` API endpoint, handle API‑key loading,
        and normalize vector shapes into the unified PKE embedding format.

    • HuggingFace
        Local or hosted transformer models offering flexible deployment
        options. The HuggingFace provider will support both pipeline‑based
        inference and model‑specific tokenization, enabling offline or
        self‑hosted embedding generation when required by enterprise or
        privacy constraints.

    • Cohere
        High‑quality text embeddings with strong clustering and semantic
        similarity performance. The Cohere provider will wrap the `/embed`
        endpoint, manage authentication, and support batch embedding
        generation. Cohere models often produce 4096‑dimensional vectors,
        so the provider will normalize output shapes to match the unified
        embedding interface used throughout the PKE system.

and will handle:

    • provider selection
    • batching
    • retries and backoff
    • rate‑limit handling
    • caching

The key design goal is to give the rest of the codebase (CLI, ingestion
pipeline, tests) a stable, provider‑agnostic API:

    from pke.embedding import EmbeddingClient

    client = EmbeddingClient(provider="deterministic")
    vector = client.generate("some text")
"""

from typing import List

# Import the deterministic stub as the current default provider.
from .deterministic import compute_embedding


class EmbeddingClient:
    """
    Minimal embedding client abstraction.

    Parameters
    ----------
    provider : str, optional
        Name of the embedding provider to use. Currently, only
        "deterministic" is supported. This parameter exists to keep
        the public API stable as additional providers are added.

    Examples
    --------
    Basic usage with the deterministic provider:

        client = EmbeddingClient(provider="deterministic")
        embedding = client.generate("example text")

    In the future, you might be able to do:

        client = EmbeddingClient(provider="openai")
        embedding = client.generate("example text")
    """

    def __init__(self, provider: str = "deterministic") -> None:
        self.provider = provider

        # For now, we only support the deterministic provider.
        # This check makes it explicit and fails loudly if someone
        # tries to use a provider that doesn't exist yet.
        if provider != "deterministic":
            raise NotImplementedError(
                f"Provider '{provider}' is not implemented yet. "
                "Currently supported: 'deterministic'."
            )

    # ------------------------------------------------------------------
    # Canonical embedding method
    # ------------------------------------------------------------------
    def generate(self, text: str) -> List[float]:
        """
        Generate an embedding vector for the given text.

        Parameters
        ----------
        text : str
            The input text to embed. In production, this would typically be
            cleaned and normalized note content from the ingestion pipeline.

        Returns
        -------
        List[float]
            A 1536-dimensional embedding vector.

        Notes
        -----
        Today, this method simply delegates to the deterministic stub
        implementation. In the future, this method will route to different
        provider-specific implementations based on `self.provider`.
        """
        return compute_embedding(text)

    # ------------------------------------------------------------------
    # Backwards‑compatible alias for CLI and legacy code
    # ------------------------------------------------------------------
    def embed(self, text: str) -> List[float]:
        """
        Backwards‑compatible alias for generate().

        The CLI historically called `embed()`, so this method ensures
        older code continues to work even as the embedding subsystem
        evolves. All new code should call `generate()`, but both methods
        are guaranteed to behave identically.
        """
        return self.generate(text)
