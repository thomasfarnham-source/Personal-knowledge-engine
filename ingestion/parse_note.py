from datetime import datetime
import os
import re
from typing import Any, Dict, Optional

import frontmatter


def parse_note(filepath: str) -> Dict[str, Any]:
    """
    Parses a Joplin-exported .md file and returns a structured dictionary.
    """
    post = frontmatter.load(filepath)
    note_id = os.path.splitext(os.path.basename(filepath))[0]

    # Extract metadata
    title: str = post.get("title", "")
    body: str = post.content
    created_at = _parse_timestamp(post.get("created_time"))
    updated_at = _parse_timestamp(post.get("updated_time"))
    deleted_time = _parse_timestamp(post.get("deleted_time"))
    user_created_time = _parse_timestamp(post.get("user_created_time"))
    user_updated_time = _parse_timestamp(post.get("user_updated_time"))
    is_conflict: bool = post.get("is_conflict", 0) == 1
    source: Optional[str] = post.get("source")
    source_application: Optional[str] = post.get("source_application")
    markup_language: int = post.get("markup_language", 1)

    # Extract resource IDs from body
    resource_ids = re.findall(r":/([a-f0-9]{32})", body)

    return {
        "id": note_id,
        "title": title,
        "body": body,
        "created_at": created_at,
        "updated_at": updated_at,
        "deleted_time": deleted_time,
        "user_created_time": user_created_time,
        "user_updated_time": user_updated_time,
        "is_conflict": is_conflict,
        "source": source,
        "source_application": source_application,
        "markup_language": markup_language,
        "resource_ids": resource_ids,
    }


def _parse_timestamp(ts: Any) -> Optional[datetime]:
    """
    Converts a Joplin timestamp (milliseconds since epoch) to a datetime object.
    Returns None if the input is None or invalid.
    """
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts) / 1000.0)
    except Exception:
        return None
