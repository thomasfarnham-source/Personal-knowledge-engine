"""
pke/api/models/query.py

Pydantic models for the PKE retrieval API.

These models define and enforce the contract between the API caller
(Obsidian plugin, CLI, or any HTTP client) and the retrieval engine.

QueryRequest  — validated input to POST /query
QueryResult   — a single retrieval result with full provenance
QueryResponse — the full API response envelope

WHY PYDANTIC:
    Pydantic validates incoming request data automatically and
    serializes outgoing response data to JSON. If a request is
    malformed, Pydantic raises a clear 422 error before any
    retrieval logic runs. This keeps the retriever clean and
    free of defensive validation code.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """
    Validated input to POST /query.

    query       — the text to search for semantically
    notebook    — optional filter by notebook name
    date_from   — optional lower bound on entry_timestamp (YYYY-MM-DD)
    date_to     — optional upper bound on entry_timestamp (YYYY-MM-DD)
    limit       — number of results to return (default 5, max 20)
    """

    query: str = Field(..., min_length=1)
    notebook: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=20)


class QueryResult(BaseModel):
    """
    A single retrieval result with full provenance metadata.

    Every field needed by the Obsidian insight panel to:
        • display the result (note_title, notebook, matched_text)
        • link back to the exact source location (note_id, chunk_index)
        • surface media (resource_ids)
        • provide temporal context (entry_timestamp)
        • distinguish chunk vs note-level results (result_type)

    The insight panel is never a dead end — note_id enables deep
    linking back to the exact source note in Obsidian.
    """

    note_id: str
    note_title: str
    notebook: str
    matched_text: str
    similarity_score: float
    chunk_index: Optional[int] = None
    section_title: Optional[str] = None
    entry_timestamp: Optional[str] = None
    resource_ids: List[str] = []
    result_type: str = "chunk"  # "chunk" or "note"


class QueryResponse(BaseModel):
    """
    Full API response envelope.

    Wraps the result list with the original query text so the
    caller always has full context alongside the results.
    """

    query: str
    results: List[QueryResult]
