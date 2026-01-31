"""
Deterministic embedding stub used during local development and testing.

This module provides a lightweight, offline replacement for a real embedding
provider (e.g., OpenAI, Hugging Face, Cohere). It allows the ingestion and
upsert pipelines to run end‑to‑end without requiring:

    • network access
    • API keys or environment variables
    • rate limits or external dependencies

The goal is to simulate the *shape* and *behavior* of a real embedding vector:
    • fixed dimensionality (1536)
    • deterministic output for identical inputs
    • input‑sensitive variation for different inputs
    • normalized to unit length

This enables:
    • reproducible tests
    • stable snapshots
    • predictable behavior in local pipelines
    • validation of vector storage and retrieval logic

This stub is intentionally simple and dependency‑free. It is not intended to
approximate semantic similarity — that will be introduced when real providers
(OpenAI, HuggingFace, Cohere) are integrated in later milestones.
"""

from typing import List


def compute_embedding(text: str) -> List[float]:
    """
    Compute a deterministic, input‑sensitive embedding vector.

    Parameters
    ----------
    text : str
        The input text to embed. In production, this would be the cleaned,
        normalized note content produced by the ingestion pipeline.

    Returns
    -------
    List[float]
        A 1536‑dimensional vector of floats. The vector is:
            • deterministic — same input → same output
            • input‑sensitive — different input → different output
            • normalized — unit length, similar to real embedding models

    Design Notes
    ------------
    This stub intentionally avoids any external dependencies. Instead, it
    converts the input text into bytes and distributes the byte values across
    the vector in a repeatable pattern. The modulo operations ensure that:

        • the vector length is fixed
        • the distribution is stable
        • the output varies meaningfully with input

    This is sufficient for:
        • verifying ingestion → embedding → upsert pipelines
        • testing vector storage schemas
        • validating that different notes produce different embeddings

    It is *not* intended to approximate semantic similarity. That will come
    when the real embedding provider is integrated.
    """

    # Fixed dimensionality chosen to match OpenAI's text-embedding-3-large.
    dim = 1536

    # Initialize the vector with zeros.
    vec = [0.0] * dim

    # ----------------------------------------------------------------------
    # Distribute byte values across the vector.
    #
    # Each byte contributes a small normalized value to a position determined
    # by its index modulo the embedding dimension. This ensures:
    #
    #   • deterministic behavior
    #   • stable distribution
    #   • meaningful variation with input
    #
    # The modulo 97 normalization keeps values in [0, 1).
    # ----------------------------------------------------------------------
    for i, ch in enumerate(text.encode("utf-8")):
        vec[i % dim] += (ch % 97) / 97.0

    # ----------------------------------------------------------------------
    # Normalize the vector to unit length.
    #
    # This simulates the behavior of real embedding models, which typically
    # output normalized vectors to improve cosine similarity behavior.
    #
    # The `or 1.0` guard prevents division by zero for empty input.
    # ----------------------------------------------------------------------
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]
