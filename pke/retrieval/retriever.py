"""
pke/retrieval/retriever.py

Hybrid retrieval logic for the PKE query API.

Strategy:
    1. Embed the query text via OpenAI text-embedding-3-small
    2. Search chunks table via match_chunks RPC (pgvector)
    3. Search notes table via match_notes RPC (fallback for
       notes with no chunk-level embeddings)
    4. Search retrieval_units table via match_retrieval_units RPC
       (email bursts and future unified content)
    5. Merge results and rank by similarity score
    6. Return top N QueryResult objects

WHY HYBRID:
    Notes above the chunking threshold are split into chunks —
    each chunk gets its own embedding and is a more precise
    retrieval target than the whole note. Notes below the
    threshold are not chunked and their note-level embedding
    is sufficient. The hybrid strategy ensures all notes are
    retrievable regardless of whether they were chunked.

    Retrieval units extend the same principle to multi-source
    content (email, and eventually backfilled iMessage bursts
    and Joplin chunks). All sources compete on similarity
    score — the panel shows what's most relevant regardless
    of origin.

SCORING HOOK:
    The _score() method is intentionally isolated. Currently it
    returns raw cosine similarity. Future iterations can layer in
    additional signals — recency decay, archetype weighting,
    timestamp confidence — without restructuring the retrieval
    logic.
"""

from typing import List, Optional

from pke.api.models.query import QueryResult
from pke.embedding.openai_client import OpenAIEmbeddingClient
from pke.supabase_client import SupabaseClient


class Retriever:
    """
    Hybrid retriever combining chunk-level, note-level, and
    retrieval-unit similarity search.

    Parameters
    ----------
    supabase_client  : SupabaseClient wrapping the Supabase connection
    embedding_client : OpenAIEmbeddingClient for query embedding generation
    chunk_limit      : max chunk candidates to fetch before re-ranking
    note_limit       : max note-level fallback candidates to fetch
    ru_limit         : max retrieval_unit candidates to fetch
    """

    def __init__(
        self,
        supabase_client: SupabaseClient,
        embedding_client: OpenAIEmbeddingClient,
        chunk_limit: int = 10,
        note_limit: int = 5,
        ru_limit: int = 10,
    ) -> None:
        self.supabase = supabase_client
        self.embedder = embedding_client
        self.chunk_limit = chunk_limit
        self.note_limit = note_limit
        self.ru_limit = ru_limit

    def query(
        self,
        query_text: str,
        notebook: Optional[str] = None,
        limit: int = 5,
    ) -> List[QueryResult]:
        """
        Execute a hybrid semantic query and return ranked results.

        Parameters
        ----------
        query_text : the raw query string from the Obsidian plugin or CLI
        notebook   : optional notebook name filter
        limit      : number of results to return after re-ranking

        Returns
        -------
        List[QueryResult] ranked by similarity score descending,
        capped at limit.
        """

        # Step 1 — embed the query text
        query_embedding = self.embedder.generate(query_text)

        # Step 2 — search chunks (primary)
        chunk_rows = self.supabase.match_chunks(
            query_embedding=query_embedding,
            match_count=self.chunk_limit,
            filter_notebook=notebook,
        )

        # Step 3 — search notes (fallback)
        # match_notes only returns notes with no chunk embeddings,
        # so there is no overlap with chunk results.
        note_rows = self.supabase.match_notes(
            query_embedding=query_embedding,
            match_count=self.note_limit,
            filter_notebook=notebook,
        )

        # Step 4 — search retrieval_units (email, future sources)
        ru_rows = self._search_retrieval_units(
            query_embedding=query_embedding,
            match_count=self.ru_limit,
            filter_notebook=notebook,
        )

        # Step 5 — build unified result list
        results: List[QueryResult] = []

        for row in chunk_rows:
            results.append(
                QueryResult(
                    note_id=str(row["note_id"]),
                    note_title=row["note_title"],
                    notebook=row["notebook"],
                    matched_text=row["chunk_text"],
                    similarity_score=self._score(row),
                    chunk_index=row.get("chunk_index"),
                    section_title=row.get("section_title"),
                    entry_timestamp=row.get("entry_timestamp"),
                    resource_ids=row.get("resource_ids") or [],
                    result_type="chunk",
                )
            )

        for row in note_rows:
            results.append(
                QueryResult(
                    note_id=str(row["note_id"]),
                    note_title=row["note_title"],
                    notebook=row["notebook"],
                    matched_text=row["note_text"],
                    similarity_score=self._score(row),
                    result_type="note",
                )
            )

        for row in ru_rows:
            results.append(
                QueryResult(
                    note_id=str(row.get("id", "")),
                    note_title=row.get("title", "") or "",
                    notebook=row.get("notebook", "") or "",
                    matched_text=row.get("body", ""),
                    similarity_score=self._score(row),
                    entry_timestamp=(
                        str(row.get("created_at", "")) if row.get("created_at") else None
                    ),
                    result_type=row.get("source_type", "email"),
                )
            )

        # Step 6 — sort by score descending, return top N
        results.sort(key=lambda r: r.similarity_score, reverse=True)
        return results[:limit]

    def _search_retrieval_units(
        self,
        query_embedding: List[float],
        match_count: int = 10,
        filter_notebook: Optional[str] = None,
    ) -> List[dict]:
        """
        Search retrieval_units via the match_retrieval_units RPC.

        Falls back gracefully if the RPC or table doesn't exist yet
        (e.g. migration not run, or no data).
        """
        try:
            client = self.supabase._require_client()
            resp = client.rpc(
                "match_retrieval_units",
                {
                    "query_embedding": query_embedding,
                    "match_count": match_count,
                    "filter_notebook": filter_notebook,
                    "max_privacy_tier": 3,
                },
            ).execute()
            return resp.data or []
        except Exception:
            # If match_retrieval_units RPC doesn't exist yet,
            # fail silently — chunks and notes still work.
            return []

    def _score(self, row: dict) -> float:
        """
        Scoring hook. Currently returns raw cosine similarity.

        Isolated here so future signals can be incorporated without
        restructuring the query() method:
            - recency decay (weight recent entries higher)
            - archetype weighting (oral history vs journal)
            - timestamp confidence (explicit > calculated > null)
        """
        return float(row["similarity"])
