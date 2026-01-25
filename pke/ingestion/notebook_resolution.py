"""
Notebook resolution stub.

The orchestrator expects a function that takes parsed notes and returns
a mapping suitable for client.upsert_notebooks().
"""

from typing import Any, Dict, List


def resolve_notebook_ids(parsed_notes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Resolve notebook identifiers from parsed notes.

    Stub behavior:
        - Look for note["notebook"] or note["metadata"].get("notebook")
        - Build a mapping: notebook_name -> {"name": notebook_name}

    Real implementation would normalize notebook metadata.
    """
    notebooks: Dict[str, Dict[str, Any]] = {}

    for note in parsed_notes:
        nb = note.get("notebook") or note.get("metadata", {}).get("notebook")
        if not nb:
            continue

        if nb not in notebooks:
            notebooks[nb] = {"name": nb}

    return notebooks
