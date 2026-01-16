# pke/embedding.py

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
    • different outputs for different inputs
    • normalized to unit length

This enables:
    • reproducible tests
    • stable snapshots
    • predictable behavior in local pipelines
    • validation of vector storage and retrieval logic

When deploying to production, this module should be replaced with a real
embedding provider that generates semantically meaningful vectors.
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
    dim = 1536
    vec = [0.0] * dim

    # Encode the input text as bytes and distribute values across the vector.
    # Each byte contributes a small normalized value to a position determined
    # by its index modulo the embedding dimension.
    for i, ch in enumerate(text.encode("utf-8")):
        vec[i % dim] += (ch % 97) / 97.0  # Normalize byte value into [0, 1)

    # Normalize the vector to unit length to simulate real embedding behavior.
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]
