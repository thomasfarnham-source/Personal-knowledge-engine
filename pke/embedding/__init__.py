"""
Public API for the embedding subsystem.

This package provides a stable import surface for embedding functionality.
Callers can rely on:

    from pke.embedding import compute_embedding
    from pke.embedding import EmbeddingClient

without needing to know anything about the internal module layout.

The internal structure of the embedding subsystem is intentionally flexible
and may evolve to support multiple providers (OpenAI, HuggingFace, Cohere),
batching, caching, and rate‑limit handling. This file ensures that external
code remains stable even as the internals change.
"""

# Re-export the deterministic embedding function.
# This is the current default provider used during local development.
from .deterministic import compute_embedding

# Re-export the provider‑agnostic embedding client abstraction.
from .embedding_client import EmbeddingClient

# Define the public API surface for `from pke.embedding import *`
__all__ = [
    "compute_embedding",
    "EmbeddingClient",
]
