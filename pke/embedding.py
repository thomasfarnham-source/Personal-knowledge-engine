# pke/embedding.py

from typing import List


def compute_embedding(text: str) -> List[float]:
    """
    Deterministic embedding stub for local testing.

    This function returns a 1536-dimensional float vector that varies with input,
    allowing tests to verify that different inputs produce different embeddings.

    It is still offline and deterministic — the same input will always yield the same output,
    but different inputs will produce different vectors.

    Replace this with a real embedding provider (e.g., OpenAI, Hugging Face)
    when deploying to production.
    """
    dim = 1536
    vec = [0.0] * dim

    # Encode the input text as bytes and distribute values across the vector
    for i, ch in enumerate(text.encode("utf-8")):
        vec[i % dim] += (ch % 97) / 97.0  # Normalize byte value into [0, 1)

    # Normalize the vector to unit length to simulate real embeddings
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]
