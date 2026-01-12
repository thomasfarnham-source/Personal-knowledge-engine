# pke/embedding.py

from typing import List


def compute_embedding(text: str) -> List[float]:
    """
    Deterministic embedding stub for local testing.

    This function returns a fixed 1536-dimensional float vector regardless of input.
    It's used to simulate real embeddings during development and testing,
    without requiring external API calls or network access.

    Replace this with a real embedding provider (e.g., OpenAI, Hugging Face)
    when deploying to production.
    """
    return [
        0.001 * (i + 1) for i in range(1536)
    ]  # Simple predictable vector: [0.001, 0.002, ..., 1.536]
