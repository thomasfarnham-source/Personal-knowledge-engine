# pke/supabase/dummy_client.py


class DummyClient:
    """
    A lightweight stand‑in for the real Supabase client.

    This client is intentionally minimal. It allows the CLI ingestion pipeline
    (Milestone 7.4) to run end‑to‑end without requiring:
      • network access
      • environment variables
      • a running Supabase instance
      • authentication tokens

    The goal is to validate the *shape* of the pipeline:
      parsed_notes.json → CLI → client.upsert_note()

    Later, in Milestone 7.5, this class will be swapped with a real client
    implementation that performs actual network writes.
    """

    def upsert_note(self, note: dict) -> None:
        """
        Simulate inserting or updating a note in Supabase.

        Parameters
        ----------
        note : dict
            A parsed note object produced by the ingestion pipeline.
            Expected keys include:
              • 'id'       — unique identifier
              • 'title'    — human‑readable title
              • 'content'  — normalized text
              • ...plus any metadata fields

        Behavior
        --------
        Instead of performing a network call, this method prints a message
        describing what *would* have been sent to Supabase. This allows you to:

          • verify the CLI is loading notes correctly
          • confirm the normalized schema is correct
          • test the ingestion loop without side effects
          • run unit tests without mocking network clients

        This is intentionally side‑effect‑free and safe to run repeatedly.
        """
        print(
            f"[DummyClient] Would upsert note: {note['id']} "
            f"(title: {note.get('title', 'Untitled')})"
        )
