"""
Public ingestion API surface.

This module exposes the stable, supported entry points for the ingestion
pipeline. External callers (CLI, services, tests) should import from here
rather than reaching into submodules directly.

The ingestion subsystem includes:
    • ingest_notes — main orchestrator entry point
    • IngestionReport — minimal reporting structure

Additional helpers (tag resolution, resource resolution, Supabase client)
are intentionally not re‑exported to keep the public surface clean.
"""

from .orchestrator import ingest_notes, IngestionReport

__all__ = [
    "ingest_notes",
    "IngestionReport",
]
