"""
Notebook resolution stub.

The orchestrator expects a function that takes parsed notes and returns
a mapping suitable for client.upsert_notebooks().
"""

from typing import Any, Dict, List


def resolve_notebook_ids(parsed_notes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Resolve notebook identifiers from parsed notes.

    Updated behavior (Feb 2026):
        - Look for note["notebook"] or note["metadata"].get("notebook")
        - Build a mapping: notebook_title -> {"title": notebook_title}
        - Fully aligned with the Supabase schema and orchestrator contract
    """
    notebooks: Dict[str, Dict[str, Any]] = {}

    for note in parsed_notes:
        nb = note.get("notebook") or note.get("metadata", {}).get("notebook")
        if not nb:
            continue

        if nb not in notebooks:
            notebooks[nb] = {"title": nb}

    return notebooks
