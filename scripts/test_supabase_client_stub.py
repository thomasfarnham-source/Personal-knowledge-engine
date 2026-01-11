# test_supabase_client_stub.py
# Quick local test for supabase_client.SupabaseClient using a deterministic
# embedding stub and a minimal DummyClient that mimics the supabase client API.
#
# Usage (from project root):
#   PYTHONPATH=. python test_supabase_client_stub.py
#
# The script imports SupabaseClient from supabase_client
# (so ensure supabase_client.py is in the project root).

from typing import Any
from supabase_client import SupabaseClient


class DummyClient:
    """
    Minimal fake Supabase client implementing the chain:
      client.table(table_name).upsert(record).execute()
    The execute() method returns an object with .data and .error attributes
    to match the shape expected by SupabaseClient.upsert_note_with_embedding.
    """

    def table(self, name: str) -> Any:
        class TableProxy:
            def upsert(self, rec: Any) -> Any:
                class ExecProxy:
                    def execute(self_inner) -> Any:
                        # Normalize to a list of records to match typical client behavior
                        data = rec if isinstance(rec, list) else [rec]
                        # Return a simple object with .data and .error attributes
                        return type("Resp", (), {"data": data, "error": None})

                return ExecProxy()

        return TableProxy()


def main() -> None:
    # Instantiate the wrapper with the dummy client so no network calls occur.
    sc = SupabaseClient(client=DummyClient())

    # Example payload to upsert
    title = "Test Title"
    body = "this is a test body"
    metadata = {"src": "local"}

    # Call the method under test
    res = sc.upsert_note_with_embedding(title=title, body=body, metadata=metadata)

    # Print the returned record(s) and verify embedding length
    print("Upsert returned:", res)
    # res is expected to be a list of records
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
