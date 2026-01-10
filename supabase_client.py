from typing import List, Any, Dict, Optional


# -------------------------
# Embedding provider stub
# -------------------------
# compute_embedding is a deterministic, local-only stub used for testing.
# It returns a fixed-length vector (1536) so you can validate vector flows
# without calling an external embedding API.
def compute_embedding(text: str) -> List[float]:
    """
    Deterministic embedding stub for local testing.
    Returns a 1536-length float vector; same input => same output.
    Replace with a real provider before production.
    """
    dim = 1536
    vec = [0.0] * dim

    # Return zero vector for empty input to keep behavior predictable.
    if not text:
        return vec

    # Convert text to bytes and fold byte values into the vector positions.
    # Using modulo 97 keeps values small and deterministic across runs.
    for i, ch in enumerate(text.encode("utf-8")):
        vec[i % dim] += (ch % 97) / 97.0

    # Normalize the vector to unit length to mimic typical embedding outputs.
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


# -------------------------
# Minimal Supabase client wrapper for tests
# -------------------------
# This class is intentionally small: it expects an injected `client` object
# that implements the minimal chain used in tests:
#   client.table(table_name).upsert(record).execute()
#
# In production you would replace this wrapper with one that uses the real
# Supabase client and handles auth, errors, and other behaviors.
class SupabaseClient:
    """
    Minimal wrapper used for local testing. Expects an injected `client`
    that implements table(name).upsert(record).execute().
    """

    def __init__(self, client: Optional[Any] = None):
        # Store the injected client (DummyClient in tests or real client in prod)
        self.client = client

    def upsert_note_with_embedding(
        self,
        title: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
        id: Optional[str] = None,
        table: str = "notes",
    ) -> Any:
        """
        Compute an embedding for `body`, build a record, and upsert it into
        the provided table via the injected client.

        Returns the .data attribute from the client's execute() response.
        Raises RuntimeError if no client is provided or if the client returns an error.
        """
        # Basic validation to avoid computing embeddings for empty content.
        if not body:
            raise ValueError("body must be provided")

        # Compute embedding using the deterministic stub.
        emb = compute_embedding(body)

        # Construct the record payload. Keep metadata default to an empty dict.
        record = {
            "title": title,
            "body": body,
            "metadata": metadata or {},
            "embedding": emb,
        }

        # Optionally include an id if provided.
        if id:
            record["id"] = id

        # Ensure a client was injected; tests inject a DummyClient.
        if not self.client:
            raise RuntimeError("No client provided to SupabaseClient")

        # Call the client's upsert path and execute the request.
        resp = self.client.table(table).upsert(record).execute()

        # If the client returned an error attribute, raise an exception.
        if getattr(resp, "error", None):
            raise RuntimeError(f"Upsert error: {resp.error}")

        # Return the data payload (expected to be a list of records).
        return resp.data
