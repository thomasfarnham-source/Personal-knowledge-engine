"""
pke/api/main.py

FastAPI application entry point for the PKE retrieval API.

Dependencies are wired once at startup and shared across requests.
The retriever is constructed with a real SupabaseClient and
OpenAIEmbeddingClient, both reading credentials from .env.

Usage:
    uvicorn pke.api.main:app --reload

WHY UVICORN:
    Uvicorn is an ASGI server — the runtime that actually listens
    for HTTP requests and hands them to FastAPI. FastAPI defines
    the routes and logic. Uvicorn runs it. The --reload flag
    restarts the server automatically when code changes, which
    is useful during development.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from supabase import create_client

from pke.api.routes.query import router as query_router
from pke.embedding.openai_client import OpenAIEmbeddingClient
from pke.retrieval.retriever import Retriever
from pke.supabase_client import SupabaseClient

load_dotenv()

app = FastAPI(title="PKE Retrieval API", version="0.1.0")

# ------------------------------------------------------------------
# Dependency wiring — constructed once at startup, shared across
# all requests. This avoids re-creating clients on every request
# which would be expensive (new HTTP connections, new API clients).
# ------------------------------------------------------------------
_raw_client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
)
_embedding_client = OpenAIEmbeddingClient(
    api_key=os.environ["OPENAI_API_KEY"],
)
_supabase_client = SupabaseClient(
    client=_raw_client,
    embedding_client=_embedding_client,
)
retriever = Retriever(
    supabase_client=_supabase_client,
    embedding_client=_embedding_client,
)

app.include_router(query_router)
