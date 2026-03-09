"""
pke/api/routes/query.py

POST /query endpoint for the PKE retrieval API.

Intentionally thin — all retrieval logic lives in
pke/retrieval/retriever.py. This route only handles:
    • request validation (delegated to Pydantic)
    • calling the retriever
    • wrapping the response
    • surfacing errors as HTTP exceptions
"""

from fastapi import APIRouter, HTTPException

from pke.api.models.query import QueryRequest, QueryResponse

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    """
    Semantic search across the PKE knowledge base.

    Accepts a natural language query and optional filters.
    Returns ranked results with full provenance metadata for
    the Obsidian insight panel.

    Raises 500 if retrieval fails for any reason.
    """
    try:
        from pke.api.main import retriever

        results = retriever.query(
            query_text=request.query,
            notebook=request.notebook,
            limit=request.limit,
        )
        return QueryResponse(query=request.query, results=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
