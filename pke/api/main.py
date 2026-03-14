"""
pke/api/main.py

FastAPI application entry point for the PKE retrieval API.

═══════════════════════════════════════════════════════════════════
WHAT THIS FILE DOES
═══════════════════════════════════════════════════════════════════

This file is the front door of the PKE retrieval API. It does
three things:

    1. Creates the FastAPI application
    2. Adds CORS middleware so Obsidian can call the API
    3. Wires up all dependencies (database, embedding client,
       retriever) once at startup and shares them across requests

It is intentionally thin. All route logic lives in
pke/api/routes/query.py. All retrieval logic lives in
pke/retrieval/retriever.py. This file just assembles the pieces.

═══════════════════════════════════════════════════════════════════
HOW TO RUN
═══════════════════════════════════════════════════════════════════

    uvicorn pke.api.main:app --reload

    pke.api.main  — the Python module path to this file
    app           — the FastAPI instance defined below
    --reload      — restart automatically when code changes
                    (development only — do not use in production)

═══════════════════════════════════════════════════════════════════
WHY UVICORN
═══════════════════════════════════════════════════════════════════

FastAPI defines the routes and logic — it is the brain.
Uvicorn is the ASGI server — it is the nervous system that:
    - Opens a port on the machine (default: 8000)
    - Listens for incoming HTTP requests
    - Hands each request to FastAPI
    - Returns FastAPI's response to the caller

Without uvicorn, FastAPI is just code sitting in a file.
Uvicorn is what makes it a running, reachable service.

═══════════════════════════════════════════════════════════════════
WHY CORS MIDDLEWARE IS REQUIRED
═══════════════════════════════════════════════════════════════════

CORS stands for Cross-Origin Resource Sharing.

Browsers and browser-based applications (including Obsidian, which
is built on Electron — a browser runtime) enforce a security rule
called the Same-Origin Policy. This rule says:

    A page at origin A is not allowed to make HTTP requests
    to origin B unless origin B explicitly permits it.

An "origin" is defined as the combination of protocol + domain +
port. For example:
    http://localhost:8000   — the PKE API
    app://obsidian.md       — Obsidian's internal origin

These are different origins. Without CORS middleware, every request
from the Obsidian plugin to the PKE API is blocked by the browser
security model before it even reaches FastAPI. The error in the
browser console looks like:

    Access to fetch at 'http://localhost:8000/query' from origin
    'app://obsidian.md' has been blocked by CORS policy: No
    'Access-Control-Allow-Origin' header is present.

The fix is to add CORSMiddleware to FastAPI. This middleware adds
the correct HTTP headers to every response, telling the browser:

    "Requests from these specific origins are permitted."

WHY WE DO NOT USE allow_origins=["*"]:
    The wildcard "*" allows any origin to call the API — including
    any website or application on the machine. Given that this API
    serves personal journal content, family history, and medical
    notes, allowing unrestricted access is inappropriate. We
    explicitly list only the origins we trust:
        app://obsidian.md   — the Obsidian plugin
        http://localhost    — local development tools
        http://127.0.0.1    — local development tools (numeric form)

═══════════════════════════════════════════════════════════════════
WHY DEPENDENCIES ARE WIRED ONCE AT STARTUP
═══════════════════════════════════════════════════════════════════

The retriever, embedding client, and Supabase client are all
constructed once when the server starts — not on every request.

This matters because each client construction is expensive:
    - SupabaseClient opens an HTTP connection to Supabase
    - OpenAIEmbeddingClient initialises an API client
    - Retriever holds references to both

If we constructed these on every request, a busy server would
open and close hundreds of connections per minute. Constructing
once and reusing across requests keeps the server fast and the
connection count low.

The tradeoff: if credentials change (e.g. a new API key), the
server must be restarted to pick them up. This is acceptable
for a local personal tool.

═══════════════════════════════════════════════════════════════════
RELATIONSHIP TO OTHER FILES
═══════════════════════════════════════════════════════════════════

    pke/api/routes/query.py     — POST /query route handler
    pke/api/models/query.py     — QueryRequest and QueryResponse
    pke/retrieval/retriever.py  — semantic search logic
    pke/supabase_client.py      — database operations
    pke/embedding/openai_client.py — embedding generation
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client

from pke.api.routes.query import router as query_router
from pke.embedding.openai_client import OpenAIEmbeddingClient
from pke.retrieval.retriever import Retriever
from pke.supabase_client import SupabaseClient

# Load environment variables from .env file.
# This must happen before any os.environ reads below.
# Variables loaded: SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY
load_dotenv()

# ------------------------------------------------------------------
# FastAPI application instance.
# Title and version appear in the auto-generated /docs interface.
# ------------------------------------------------------------------
app = FastAPI(title="PKE Retrieval API", version="0.1.0")

# ------------------------------------------------------------------
# CORS middleware.
#
# Must be added before any routes are registered. FastAPI processes
# middleware in the order it is added — CORS headers need to be
# present on every response including error responses, so this
# goes first.
#
# allow_origins   — which origins are permitted to call the API
# allow_methods   — which HTTP methods are permitted
# allow_headers   — which request headers are permitted
#
# The Content-Type header is required because our plugin sends
# POST requests with a JSON body:
#     Content-Type: application/json
# Without allowing this header, the browser rejects the preflight.
#
# A "preflight" is an automatic OPTIONS request the browser sends
# before any cross-origin POST to ask: "are you going to accept
# this?" The CORS middleware handles preflight responses
# automatically.
# ------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "app://obsidian.md",    # Obsidian desktop plugin origin
        "http://localhost",     # local dev tools
        "http://127.0.0.1",     # local dev tools (numeric form)
    ],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

# ------------------------------------------------------------------
# Dependency wiring.
#
# All clients are constructed once at startup and reused across
# every request. See module docstring for rationale.
#
# Construction order matters:
#   1. Raw Supabase client  — needs SUPABASE_URL and SUPABASE_KEY
#   2. Embedding client     — needs OPENAI_API_KEY
#   3. SupabaseClient       — wraps raw client + embedding client
#   4. Retriever            — wraps SupabaseClient + embedding client
#
# The retriever is the only object the route handler needs.
# It is imported by name in pke/api/routes/query.py:
#     from pke.api.main import retriever
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

# ------------------------------------------------------------------
# Route registration.
# The query router adds POST /query to the application.
# Additional routers (future milestones) would be added here.
# ------------------------------------------------------------------
app.include_router(query_router)

