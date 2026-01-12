"""
Quick local test for SupabaseClient using the fully typed DummyClient.

This script verifies:
    - embedding computation,
    - NoteRecord construction,
    - and the upsert flow through SupabaseClient.

It uses the DummyClient from tests/dummy_supabase.py, which implements
SupabaseClientInterface and is fully mypy-compliant.
"""

from pke.supabase_client import SupabaseClient
from tests.dummy_supabase import DummyClient  # ✅ use the real typed dummy


def main() -> None:
    """
    Run a simple upsert test using the deterministic DummyClient.
    No network calls occur.
    """
    # Inject the fully typed dummy client
    sc = SupabaseClient(client=DummyClient())

    # Example payload to upsert
    title = "Test Title"
    body = "this is a test body"
    metadata = {"src": "local"}

    # Perform the upsert
    res = sc.upsert_note_with_embedding(title=title, body=body, metadata=metadata)

    print("Upsert returned:", res)

    # Validate embedding presence and length
    if isinstance(res, list) and res:
        emb = res[0].get("embedding")
        if emb is None:
            print("No embedding found in returned record.")
        else:
            print("Embedding length:", len(emb))
    else:
        print("Unexpected response shape:", type(res), res)


if __name__ == "__main__":
    main()
