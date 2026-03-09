"""
pke/cli/embed_chunks.py

CLI command to backfill chunk-level embeddings.

Walks all chunks where embedding IS NULL and generates embeddings
via OpenAI text-embedding-3-small. Safe to re-run — only processes
unembedded chunks. Progress logged every 50 chunks.

WHY THIS IS A SEPARATE CLI:
    Chunk embedding generation is decoupled from ingestion
    intentionally. Ingestion writes chunk text and metadata.
    Embedding generation is a separate, expensive, rate-limited
    operation that may need to be re-run independently of ingest.

Usage:
    python -m pke.cli.embed_chunks
"""

import logging
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

from pke.embedding.openai_client import OpenAIEmbeddingClient
from pke.supabase_client import SupabaseClient

load_dotenv()

logger = logging.getLogger("pke.embed_chunks")
logger.setLevel(logging.INFO)
console = logging.StreamHandler(sys.stdout)
console.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(console)


def embed_chunks() -> None:
    """
    Backfill embeddings for all chunks where embedding IS NULL.

    Fetches chunks in batches of 100 to keep memory flat regardless
    of total chunk count. Logs progress every 50 chunks. Exits
    cleanly when no unembedded chunks remain.
    """
    api_key = os.environ["OPENAI_API_KEY"]
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_KEY"]

    raw_client = create_client(supabase_url, supabase_key)
    embedding_client = OpenAIEmbeddingClient(api_key=api_key)
    client = SupabaseClient(client=raw_client, embedding_client=embedding_client)

    total = 0
    batch_size = 100

    logger.info("Starting chunk embedding backfill...")

    while True:
        # Fetch next batch of unembedded chunks
        chunks = client.fetch_unembedded_chunks(batch_size=batch_size)

        if not chunks:
            # No more unembedded chunks — we are done
            break

        for chunk in chunks:
            embedding = embedding_client.generate(chunk["chunk_text"])
            client.update_chunk_embedding(chunk["id"], embedding)
            total += 1

            if total % 50 == 0:
                logger.info(f"Embedded {total} chunks...")

    logger.info(f"Done. {total} chunks embedded.")


if __name__ == "__main__":
    embed_chunks()
