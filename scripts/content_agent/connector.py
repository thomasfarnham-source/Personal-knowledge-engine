"""
Content Curation Agent — Connector

Takes the Editor's filtered items and queries two sources for adjacency:
  1. PKE Retrieval API — personal journals, messages, email
  2. Book database — book club reading with thematic tags

The Connector does not force connections. When there is no meaningful
adjacency, the item stands on its own as curation. Silence is better
than a stretch.

Usage:
    python -m scripts.content_agent.connector
    python -m scripts.content_agent.connector --input path/to/editor_filtered.json
    python -m scripts.content_agent.connector --skip-pke
    python -m scripts.content_agent.connector --skip-books
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Connection:
    """A discovered adjacency between curated content and personal history."""

    source: str  # "pke" or "books"
    matched_text: str  # The relevant passage or book description
    title: str  # Note title or book title
    date: Optional[str]  # When the personal content was written/read
    relevance_note: str  # One-sentence description of the connection


@dataclass
class ConnectedItem:
    """An Editor item annotated with connections."""

    title: str
    url: str
    source_name: str
    pillar: str
    published: Optional[str]
    summary: Optional[str]
    editor_reason: str
    cross_pillar: list[str]
    strength: str
    item_hash: str
    connections: list[Connection]
    connection_density: int  # Number of meaningful connections found


# ---------------------------------------------------------------------------
# PKE Retrieval API queries
# ---------------------------------------------------------------------------


def query_pke(
    query_text: str, pke_url: str = "http://localhost:8000", limit: int = 3
) -> list[dict]:
    """Query the PKE retrieval API for semantically related personal content."""
    try:
        response = requests.post(
            f"{pke_url}/query",
            json={
                "query": query_text,
                "limit": limit,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except requests.RequestException as e:
        logger.warning(f"PKE query failed: {e}")
        return []


def find_pke_connections(
    item: dict, pke_url: str, min_similarity: float = 0.35
) -> list[Connection]:
    """Find personal corpus connections for a curated item."""
    # Query with the item's title + summary for semantic matching
    query_text = item["title"]
    if item.get("summary"):
        query_text += " " + item["summary"][:200]

    results = query_pke(query_text, pke_url)
    connections = []

    for result in results:
        score = result.get("similarity_score", 0)
        if score < min_similarity:
            continue

        connections.append(
            Connection(
                source="pke",
                matched_text=result.get("matched_text", "")[:300],
                title=result.get("note_title", ""),
                date=result.get("entry_timestamp"),
                relevance_note="",  # Will be filled by synthesis step
            )
        )

    return connections


# ---------------------------------------------------------------------------
# Book database queries
# ---------------------------------------------------------------------------


def load_book_database(path: Optional[Path] = None) -> list[dict]:
    """Load the book database."""
    if path is None:
        path = Path(__file__).parent / "books.json"

    if not path.exists():
        logger.info("No book database found — skipping book connections")
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("books", [])


def find_book_connections(item: dict, books: list[dict]) -> list[Connection]:
    """Find thematic connections between a curated item and the book database."""
    if not books:
        return []

    # Simple keyword matching against book themes
    # This is v1 — future versions could use embeddings
    item_text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    connections = []

    for book in books:
        themes = book.get("themes", [])
        matching_themes = [t for t in themes if t.lower() in item_text]

        if not matching_themes:
            # Check for broader keyword overlap
            keywords = book.get("keywords", [])
            matching_themes = [k for k in keywords if k.lower() in item_text]

        if matching_themes:
            connections.append(
                Connection(
                    source="books",
                    matched_text=book.get("personal_note", book.get("core_idea", "")),
                    title=f"{book['title']} by {book.get('author', 'Unknown')}",
                    date=book.get("year_read"),
                    relevance_note=f"Thematic overlap: {', '.join(matching_themes[:3])}",
                )
            )

    return connections[:2]  # Cap at 2 book connections per item


# ---------------------------------------------------------------------------
# Connection synthesis via Claude
# ---------------------------------------------------------------------------

SYNTHESIS_SYSTEM_PROMPT = """You are the Connector agent in a content curation system.
You have been given curated articles along with potential connections to personal
journal entries, messages, and books from the reader's own history.

Your job is to write a brief, natural relevance note for each connection — one
sentence that describes WHY this personal content connects to the curated article.

Do not force connections. If a connection is weak or coincidental, say so or
mark it as "weak". The reader values genuine adjacency over manufactured insight.

When a connection is strong — when the personal history illuminates the article
or the article illuminates the personal history — name it clearly.

Respond ONLY with valid JSON. No preamble, no markdown backticks.
Format:
{
  "annotated_connections": [
    {
      "item_hash": "abc123...",
      "connections": [
        {
          "index": 0,
          "relevance_note": "Your 2019 journal entry about...",
          "keep": true
        }
      ]
    }
  ]
}
"""


def synthesize_connections(items_with_connections: list[dict], api_key: str) -> dict:
    """Use Claude to write relevance notes and filter weak connections."""
    if not api_key:
        logger.warning("No API key — skipping connection synthesis")
        return {"annotated_connections": []}

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "system": SYNTHESIS_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": json.dumps(items_with_connections)}],
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]

        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]

        return json.loads(text)

    except (requests.RequestException, json.JSONDecodeError) as e:
        logger.error(f"Connection synthesis failed: {e}")
        return {"annotated_connections": []}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_connector_output(items: list[ConnectedItem], output_dir: Path) -> Path:
    """Write connected items for the Composer."""
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")

    json_path = output_dir / f"connected_{date_str}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "connect_date": date_str,
                "connect_timestamp": datetime.now(timezone.utc).isoformat(),
                "items": [asdict(item) for item in items],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    logger.info(f"Connector output written: {json_path}")
    return json_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_connector(
    input_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    pke_url: str = "http://localhost:8000",
    skip_pke: bool = False,
    skip_books: bool = False,
    dry_run: bool = False,
) -> list[ConnectedItem]:
    """Run the Connector on Editor output."""
    import os

    # Find latest Editor output
    if input_path is None:
        filtered_dir = Path(__file__).parent / "output" / "filtered"
        json_files = sorted(filtered_dir.glob("editor_filtered_*.json"), reverse=True)
        if not json_files:
            logger.error("No Editor output found. Run the Editor first.")
            return []
        input_path = json_files[0]

    logger.info(f"Loading Editor output: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        editor_data = json.load(f)

    editor_items = editor_data.get("items", [])
    logger.info(f"Items to connect: {len(editor_items)}")

    # Load book database
    books = [] if skip_books else load_book_database()
    if books:
        logger.info(f"Book database loaded: {len(books)} books")

    # Find connections for each item
    connected_items = []
    for item in editor_items:
        connections = []

        # PKE connections
        if not skip_pke:
            pke_conns = find_pke_connections(item, pke_url)
            connections.extend(pke_conns)
            if pke_conns:
                logger.info(f"  PKE: {len(pke_conns)} connections for '{item['title'][:50]}'")

        # Book connections
        if not skip_books and books:
            book_conns = find_book_connections(item, books)
            connections.extend(book_conns)
            if book_conns:
                logger.info(f"  Books: {len(book_conns)} connections for '{item['title'][:50]}'")

        connected = ConnectedItem(
            title=item["title"],
            url=item["url"],
            source_name=item["source_name"],
            pillar=item["pillar"],
            published=item.get("published"),
            summary=item.get("summary"),
            editor_reason=item.get("editor_reason", ""),
            cross_pillar=item.get("cross_pillar", []),
            strength=item.get("strength", "solid"),
            item_hash=item.get("item_hash", ""),
            connections=connections,
            connection_density=len(connections),
        )
        connected_items.append(connected)

    # Synthesize relevance notes via Claude (if connections exist)
    items_with_conns = [asdict(i) for i in connected_items if i.connections]
    if items_with_conns:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            logger.info(f"Synthesizing {len(items_with_conns)} items with connections...")
            synthesis = synthesize_connections(items_with_conns, api_key)

            # Apply relevance notes back
            synth_map = {a["item_hash"]: a for a in synthesis.get("annotated_connections", [])}
            for item in connected_items:
                if item.item_hash in synth_map:
                    annotations = synth_map[item.item_hash]
                    filtered_conns = []
                    for ann in annotations.get("connections", []):
                        idx = ann.get("index", 0)
                        if ann.get("keep", True) and idx < len(item.connections):
                            item.connections[idx].relevance_note = ann.get("relevance_note", "")
                            filtered_conns.append(item.connections[idx])
                    item.connections = filtered_conns
                    item.connection_density = len(filtered_conns)

    # Summary
    with_connections = sum(1 for i in connected_items if i.connections)
    total_connections = sum(i.connection_density for i in connected_items)
    logger.info(
        f"=== Connector Complete: {with_connections}/{len(connected_items)} items "
        f"have connections ({total_connections} total) ==="
    )

    if dry_run:
        logger.info("Dry run — no output written")
        return connected_items

    if output_dir is None:
        output_dir = Path(__file__).parent / "output" / "connected"
    write_connector_output(connected_items, output_dir)

    return connected_items


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Content Curation Agent — Connector")
    parser.add_argument("--input", type=Path, default=None, help="Path to Editor filtered JSON")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory")
    parser.add_argument("--pke-url", default="http://localhost:8000", help="PKE Retrieval API URL")
    parser.add_argument("--skip-pke", action="store_true", help="Skip PKE corpus queries")
    parser.add_argument("--skip-books", action="store_true", help="Skip book database queries")
    parser.add_argument("--dry-run", action="store_true", help="Connect but don't write output")
    args = parser.parse_args()

    run_connector(
        input_path=args.input,
        output_dir=args.output_dir,
        pke_url=args.pke_url,
        skip_pke=args.skip_pke,
        skip_books=args.skip_books,
        dry_run=args.dry_run,
    )
