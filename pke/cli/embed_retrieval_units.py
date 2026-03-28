"""
Embed Retrieval Units
=======================
Backfill embeddings for retrieval_units where embedding IS NULL.

Same pattern as embed_chunks.py but targets the unified retrieval table.

Usage:
    python -m pke.cli.embed_retrieval_units
    python -m pke.cli.embed_retrieval_units --batch-size 50
"""

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    batch_size = 50
    if "--batch-size" in sys.argv:
        idx = sys.argv.index("--batch-size")
        if idx + 1 < len(sys.argv):
            batch_size = int(sys.argv[idx + 1])

    # Wire up clients
    from supabase import create_client
    from pke.embedding.openai_client import OpenAIEmbeddingClient

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not supabase_url or not supabase_key:
        print("ERROR: Set SUPABASE_URL and SUPABASE_KEY in .env")
        sys.exit(1)
    if not openai_key:
        print("ERROR: Set OPENAI_API_KEY in .env")
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)
    embedding_client = OpenAIEmbeddingClient(openai_key)

    # Count unembedded units
    count_resp = (
        client.table("retrieval_units").select("id", count=None).is_("embedding", "null").execute()
    )
    total = len(count_resp.data) if count_resp.data else 0
    print(f"Retrieval units needing embeddings: {total}")

    if total == 0:
        print("Nothing to embed.")
        return

    embedded = 0
    errors = 0
    start_time = time.time()

    while True:
        # Fetch a batch of unembedded units
        batch_resp = (
            client.table("retrieval_units")
            .select("id, body")
            .is_("embedding", "null")
            .limit(batch_size)
            .execute()
        )

        if not batch_resp.data:
            break

        for unit in batch_resp.data:
            if not isinstance(unit, dict):
                continue
            unit_id = str(unit["id"])
            body = str(unit["body"])

            if not body.strip():
                errors += 1
                continue

            try:
                embedding = embedding_client.generate(body)
                client.table("retrieval_units").update({"embedding": embedding}).eq(
                    "id", unit_id
                ).execute()
                embedded += 1

                if embedded % 25 == 0:
                    elapsed = time.time() - start_time
                    rate = embedded / elapsed if elapsed > 0 else 0
                    remaining = (total - embedded) / rate if rate > 0 else 0
                    print(
                        f"  {embedded} / {total} embedded "
                        f"({embedded * 100 // total}%) — "
                        f"{rate:.1f}/sec — "
                        f"~{remaining / 60:.1f} min remaining"
                    )

            except Exception as e:
                errors += 1
                print(f"  Error embedding {unit_id}: {e}")
                if errors > 10:
                    print("Too many errors — stopping.")
                    break

        if errors > 10:
            break

    elapsed = time.time() - start_time
    print("\nEmbedding complete:")
    print(f"  Embedded: {embedded}")
    print(f"  Errors:   {errors}")
    print(f"  Time:     {elapsed / 60:.1f} minutes")


if __name__ == "__main__":
    main()
