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
        Compute an embedding for the note body and upsert
        the note into the specified Supabase table.

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

        if not self.client:
            raise RuntimeError(
                "No client provided to SupabaseClient. "
                "Please pass a valid client instance or use the default."
            )

        emb = compute_embedding(body)

        record: NoteRecord = {
            "title": title,
            "body": body,
            "metadata": metadata or {},
            "embedding": emb,
        }

        if id:
            record["id"] = id

        resp = self.client.table(table).upsert(record).execute()

        if getattr(resp, "error", None):
            raise RuntimeError(f"Upsert error: {resp.error}")

        return resp.data
