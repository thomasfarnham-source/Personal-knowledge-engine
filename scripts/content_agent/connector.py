"""
Content Curation Agent — Connector

Takes the Editor's filtered items and queries two sources for adjacency:
  1. PKE Retrieval API — personal journals, messages, email
  2. Book database — book club reading with thematic tags

Connections are evaluated and explained by Claude — not by keyword
matching. The Connector does not force connections. When there is no
meaningful adjacency, the item stands on its own as curation. Silence
is better than a stretch.

Usage:
    python scripts/content_agent/connector.py
    python scripts/content_agent/connector.py --input path/to/editor_filtered.json
    python scripts/content_agent/connector.py --skip-pke
    python scripts/content_agent/connector.py --skip-books
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

from dotenv import load_dotenv
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
    query_text = item["title"]
    if item.get("summary"):
        query_text += " " + (item.get("summary") or "")[:200]

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
# Book database — Claude-powered matching
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


BOOK_MATCHING_PROMPT = """You are the Connector agent in a content curation system.
You are given a set of curated articles and a library of books the reader has read.

Your job is to identify genuine intellectual connections between articles and books.
NOT word overlap. NOT surface-level theme matching. Genuine conceptual adjacency —
the kind of connection a well-read person would make in conversation.

Rules:
- Only return connections you would confidently defend to an intelligent reader
- "Power" appearing in both an article about payment networks and a book about
  political philosophy is NOT a connection
- A book about the panopticon connecting to an article about AI surveillance
  in banking IS a connection — because both examine how governance architectures
  make compliance self-enforcing
- Quality over quantity — most articles will have zero or one book connection
- If no genuine connection exists, return an empty list for that article
- For each connection, write ONE sentence explaining the intellectual relationship

Respond ONLY with valid JSON. No preamble, no markdown backticks.
Format:
{
  "book_connections": [
    {
      "item_hash": "abc123...",
      "connections": [
        {
          "book_title": "Discipline and Punish",
          "book_author": "Michel Foucault",
                    "explanation": "Both examine how governance architectures make compliance \
self-enforcing — Foucault's panopticon and the Three Lines Model serve the same \
structural function."
        }
      ]
    }
  ]
}
"""


def find_book_connections_via_claude(items: list[dict], books: list[dict], api_key: str) -> dict:
    """Use Claude to find genuine intellectual connections between articles and books."""
    if not api_key:
        logger.warning("No API key — skipping book connections")
        return {"book_connections": []}

    if not books:
        return {"book_connections": []}

    # Prepare items for Claude — title, summary, editor reason
    items_for_review = []
    for item in items:
        items_for_review.append(
            {
                "item_hash": item.get("item_hash", ""),
                "title": item["title"],
                "summary": (item.get("summary") or "")[:300],
                "editor_reason": item.get("editor_reason", ""),
            }
        )

    # Prepare books — title, author, core idea, themes
    books_for_review = []
    for book in books:
        books_for_review.append(
            {
                "title": book["title"],
                "author": book.get("author", ""),
                "core_idea": book.get("core_idea", ""),
                "themes": book.get("themes", []),
            }
        )

    user_message = (
        f"ARTICLES ({len(items_for_review)}):\n"
        f"{json.dumps(items_for_review, indent=2)}\n\n"
        f"BOOK LIBRARY ({len(books_for_review)} books):\n"
        f"{json.dumps(books_for_review, indent=2)}"
    )

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
                "system": BOOK_MATCHING_PROMPT,
                "messages": [{"role": "user", "content": user_message}],
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
        logger.error(f"Book matching API call failed: {e}")
        return {"book_connections": []}


def apply_book_connections(items: list["ConnectedItem"], book_results: dict) -> None:
    """Apply Claude's book connections to ConnectedItem objects."""
    conn_map: dict[str, list[dict]] = {}
    for entry in book_results.get("book_connections", []):
        item_hash = entry.get("item_hash", "")
        conn_map[item_hash] = entry.get("connections", [])

    for item in items:
        book_conns = conn_map.get(item.item_hash, [])
        for bc in book_conns:
            item.connections.append(
                Connection(
                    source="books",
                    matched_text=bc.get("explanation", ""),
                    title=f"{bc.get('book_title', '')} by {bc.get('book_author', '')}",
                    date=None,
                    relevance_note=bc.get("explanation", ""),
                )
            )
        item.connection_density = len(item.connections)


# ---------------------------------------------------------------------------
# Connection synthesis via Claude — PKE relevance notes
# ---------------------------------------------------------------------------

SYNTHESIS_SYSTEM_PROMPT = """You are the Connector agent in a content curation system.
You have been given curated articles along with matched passages from the reader's
personal corpus — journal entries, messages, emails, and notes spanning years.

Your job is to write a brief, specific relevance note for each personal corpus
connection — one sentence that explains WHY this personal content connects to
the curated article. Be specific. Name what the note is about and how it relates.

Rules:
- Be concrete: "Your 2017 notes on blockchain AML enforcement connect because
  both examine how regulated systems fail when actors operate outside visibility"
  is good.
- Be honest: if the connection is weak or coincidental, mark keep as false.
- Never force a connection. If the matched text has no meaningful relationship
  to the article, discard it.
- The reader is sharp and has no patience for vague connections.

Respond ONLY with valid JSON. No preamble, no markdown backticks.
Format:
{
  "annotated_connections": [
    {
      "item_hash": "abc123...",
      "connections": [
        {
          "index": 0,
          "relevance_note": "Your 2017 notes on blockchain AML...",
          "keep": true
        }
      ]
    }
  ]
}
"""


def synthesize_connections(items_with_connections: list[dict], api_key: str) -> dict:
    """Use Claude to write relevance notes and filter weak PKE connections."""
    if not api_key:
        logger.warning("No API key — skipping connection synthesis")
        return {"annotated_connections": []}

    # Build a focused payload — article info + matched texts
    synthesis_payload = []
    for item in items_with_connections:
        pke_connections = []
        for i, conn in enumerate(item.get("connections", [])):
            if conn.get("source") == "pke":
                pke_connections.append(
                    {
                        "index": i,
                        "note_title": conn.get("title", ""),
                        "date": conn.get("date"),
                        "matched_text": conn.get("matched_text", "")[:300],
                    }
                )

        if pke_connections:
            synthesis_payload.append(
                {
                    "item_hash": item.get("item_hash", ""),
                    "article_title": item.get("title", ""),
                    "article_summary": (item.get("summary") or "")[:200],
                    "pke_connections": pke_connections,
                }
            )

    if not synthesis_payload:
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
                "messages": [{"role": "user", "content": json.dumps(synthesis_payload)}],
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


def apply_synthesis(items: list["ConnectedItem"], synthesis: dict) -> None:
    """Apply Claude's relevance notes to PKE connections and remove weak ones."""
    synth_map: dict[str, list[dict]] = {}
    for entry in synthesis.get("annotated_connections", []):
        synth_map[entry.get("item_hash", "")] = entry.get("connections", [])

    for item in items:
        annotations = synth_map.get(item.item_hash, [])
        if not annotations:
            continue

        ann_map = {a["index"]: a for a in annotations}
        filtered_connections: list[Connection] = []

        for i, conn in enumerate(item.connections):
            if conn.source == "books":
                # Book connections already have explanations from the matching step
                filtered_connections.append(conn)
            elif i in ann_map:
                ann = ann_map[i]
                if ann.get("keep", False):
                    conn.relevance_note = ann.get("relevance_note", "")
                    filtered_connections.append(conn)
                # If keep is False, connection is dropped silently
            else:
                # No annotation for this connection — keep it but flag
                filtered_connections.append(conn)

        item.connections = filtered_connections
        item.connection_density = len(filtered_connections)


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

    load_dotenv()

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

    # Get API key for Claude calls
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # ---------------------------------------------------------------------------
    # Step 1: Find PKE corpus connections for each item
    # ---------------------------------------------------------------------------
    connected_items: list[ConnectedItem] = []
    for item in editor_items:
        connections: list[Connection] = []

        if not skip_pke:
            pke_conns = find_pke_connections(item, pke_url)
            connections.extend(pke_conns)
            if pke_conns:
                logger.info(f"  PKE: {len(pke_conns)} connections for '{item['title'][:50]}'")

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

    # ---------------------------------------------------------------------------
    # Step 2: Synthesize PKE connections — get relevance notes from Claude
    # ---------------------------------------------------------------------------
    items_with_pke = [
        asdict(i) for i in connected_items if any(c.source == "pke" for c in i.connections)
    ]
    if items_with_pke and api_key:
        logger.info(f"Synthesizing PKE connections for {len(items_with_pke)} items...")
        synthesis = synthesize_connections(items_with_pke, api_key)
        apply_synthesis(connected_items, synthesis)

        # Count surviving PKE connections
        pke_kept = sum(1 for i in connected_items for c in i.connections if c.source == "pke")
        pke_dropped = sum(
            1
            for entry in synthesis.get("annotated_connections", [])
            for a in entry.get("connections", [])
            if not a.get("keep", True)
        )
        logger.info(f"  PKE synthesis: {pke_kept} kept, {pke_dropped} dropped as weak")

    # ---------------------------------------------------------------------------
    # Step 3: Find book connections via Claude
    # ---------------------------------------------------------------------------
    if not skip_books and books and api_key:
        logger.info("Finding book connections via Claude...")
        book_results = find_book_connections_via_claude(editor_items, books, api_key)
        apply_book_connections(connected_items, book_results)

        book_count = sum(1 for i in connected_items for c in i.connections if c.source == "books")
        items_with_books = sum(
            1 for i in connected_items if any(c.source == "books" for c in i.connections)
        )
        logger.info(f"  Books: {book_count} connections across {items_with_books} items")

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
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
