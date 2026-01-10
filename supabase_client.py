from typing import List, Dict, Optional, Protocol, TypedDict, Any

# -------------------------
# Embedding provider stub
# -------------------------


def compute_embedding(text: str) -> List[float]:
    """
    Deterministic embedding stub for local testing.

    This function simulates a real embedding model by returning a fixed-length vector (1536 floats).
    It ensures that the same input string always produces the same output vector, which is useful
    for testing vector pipelines without relying on external APIs.

    Args:
        text: The input string to embed.

    Returns:
        A normalized 1536-dimensional float vector.
    """
    dim = 1536
    vec = [0.0] * dim

    # Return a zero vector for empty input to avoid divide-by-zero and keep behavior predictable.
    if not text:
        return vec

    # Encode text to bytes and fold byte values into vector positions using modulo arithmetic.
    for i, ch in enumerate(text.encode("utf-8")):
        vec[i % dim] += (ch % 97) / 97.0

    # Normalize the vector to unit length to mimic real embedding output.
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


# -------------------------
# Type definitions for safety and clarity
# -------------------------


class NoteRecord(TypedDict, total=False):
    """
    TypedDict representing a note record to be upserted into Supabase.
    All fields are optional to support partial updates.
    """

    id: str
    title: str
    body: str
    metadata: Dict[str, Any]
    embedding: List[float]


class SupabaseExecuteResponse(Protocol):
    """
    Protocol for the response object returned by .execute().
    Must expose .data and .error attributes.
    """

    data: Any
    error: Optional[str]


class SupabaseClientInterface(Protocol):
    """
    Protocol for the injected Supabase client.
    Must support .table(name) → TableQuery.
    """

    def table(self, name: str) -> "TableQuery": ...


class TableQuery(Protocol):
    """
    Protocol for the object returned by .table().
    Must support .upsert(record) → Executable.
    """

    def upsert(self, record: NoteRecord) -> "Executable": ...


class Executable(Protocol):
    """
    Protocol for the object returned by .upsert().
    Must support .execute() → SupabaseExecuteResponse.
    """

    def execute(self) -> SupabaseExecuteResponse: ...


# -------------------------
# Minimal Supabase client wrapper for local testing
# -------------------------


class SupabaseClient:
    """
    A minimal wrapper around an injected Supabase-like client.

    This class is designed for local testing and testability. It expects a client that implements
    the method chain: .table(name).upsert(record).execute(), and provides a single method to
    upsert a note with an embedding.

    In production, this wrapper can be extended to include authentication, retries, logging, etc.
    """

    def __init__(self, client: Optional[SupabaseClientInterface] = None):
        """
        Initialize the SupabaseClient with an optional injected client.

        Args:
            client: An object that implements the SupabaseClientInterface.
        """
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
        Compute an embedding for the note body and upsert the note into the specified Supabase table.

        Args:
            title: The note title.
            body: The note body (required for embedding).
            metadata: Optional metadata dictionary.
            id: Optional note ID (used to enforce upsert behavior).
            table: The Supabase table name (default: "notes").

        Returns:
            The .data attribute from the Supabase response.

        Raises:
            ValueError: If body is empty.
            RuntimeError: If no client is provided or if the Supabase response contains an error.
        """
        if not body:
            raise ValueError("body must be provided")

        # Generate a deterministic embedding for the note body.
        emb = compute_embedding(body)

        # Construct the record to be upserted.
        record: NoteRecord = {
            "title": title,
            "body": body,
            "metadata": metadata or {},
            "embedding": emb,
        }

        if id:
            record["id"] = id

        if not self.client:
            raise RuntimeError(
                "No client provided to SupabaseClient"
            )

        # Perform the upsert operation via the injected client.
        resp = self.client.table(table).upsert(record).execute()

        # Raise an error if the response contains an error field.
        if getattr(resp, "error", None):
            raise RuntimeError(f"Upsert error: {resp.error}")

        return resp.data


# -------------------------
# Optional: Export a default SupabaseClient instance
# -------------------------

# This allows other modules to do:
#   from supabase_client import supabase
# and use it directly, assuming a real client is injected here in production.
supabase: Optional[SupabaseClient] = None
