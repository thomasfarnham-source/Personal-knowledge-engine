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


@dataclass
class ConnectorErrors:
    """
    Errors encountered during the Connector run.

    Tracked in structured form so they can be surfaced in the output JSON
    and propagated to Pipeline Status. Each field is populated only when
    the relevant failure occurred.
    """

    # Aggregate PKE failure: if N items couldn't be queried, we record the count
    # and one representative error rather than spamming N near-identical messages.
    # When PKE is fully down, the root cause is the same for every item.
    pke_items_failed: int = 0
    pke_total_items: int = 0
    pke_sample_error: str = ""

    # Book matching is a single Claude call — either it worked or it didn't
    book_matching_error: str = ""

    # Synthesis is a single Claude call — either it worked or it didn't
    synthesis_error: str = ""

    def has_errors(self) -> bool:
        """True if any error was recorded."""
        return bool(self.pke_items_failed or self.book_matching_error or self.synthesis_error)


# ---------------------------------------------------------------------------
# PKE Retrieval API queries
# ---------------------------------------------------------------------------


def query_pke(
    query_text: str, pke_url: str = "http://localhost:8000", limit: int = 3
) -> tuple[list[dict], Optional[str]]:
    """
    Query the PKE retrieval API for semantically related personal content.

    Returns (results, error_message). On success, error_message is None.
    On failure, results is an empty list and error_message describes the failure.
    Returning errors instead of swallowing them lets the caller aggregate
    PKE failures across items rather than logging each one silently.
    """
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
        return data.get("results", []), None
    except requests.RequestException as e:
        return [], str(e)


def find_pke_connections(
    item: dict, pke_url: str, min_similarity: float = 0.35
) -> tuple[list[Connection], Optional[str]]:
    """
    Find personal corpus connections for a curated item.

    Returns (connections, error_message). Error propagates up from query_pke
    so the run loop can decide whether to log per-item or aggregate.
    """
    query_text = item["title"]
    if item.get("summary"):
        query_text += " " + (item.get("summary") or "")[:200]

    results, error = query_pke(query_text, pke_url)
    if error:
        return [], error

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
                relevance_note="",
            )
        )

    return connections, None


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
    """
    Use Claude to find genuine intellectual connections between articles and books.

    Returns a dict containing 'book_connections' on success, or with an additional
    'error' field on failure. The 'error' field is the signal to the caller that
    the API call failed entirely (as opposed to Claude finding no connections),
    so the failure can be propagated to ConnectorErrors.
    """
    if not api_key:
        return {"book_connections": [], "error": "No API key provided"}

    if not books:
        return {"book_connections": []}

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
                "model": "claude-sonnet-4-6",
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
        # Log AND surface the error via the return value. The 'error' field is
        # how the caller distinguishes "Claude returned no matches" from
        # "the call failed entirely."
        error_msg = str(e)
        logger.error(f"Book matching API call failed: {error_msg}")
        return {"book_connections": [], "error": error_msg}


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
    """
    Use Claude to write relevance notes and filter weak PKE connections.

    Returns a dict containing 'annotated_connections' on success, or with an
    additional 'error' field on failure (same pattern as book matching).
    """
    if not api_key:
        return {"annotated_connections": [], "error": "No API key provided"}

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
                "model": "claude-sonnet-4-6",
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
        error_msg = str(e)
        logger.error(f"Connection synthesis failed: {error_msg}")
        return {"annotated_connections": [], "error": error_msg}


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
                filtered_connections.append(conn)
            elif i in ann_map:
                ann = ann_map[i]
                if ann.get("keep", False):
                    conn.relevance_note = ann.get("relevance_note", "")
                    filtered_connections.append(conn)
            else:
                filtered_connections.append(conn)

        item.connections = filtered_connections
        item.connection_density = len(filtered_connections)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_connector_output(
    items: list[ConnectedItem], errors: ConnectorErrors, output_dir: Path
) -> Path:
    """
    Write connected items for the Composer.

    The output JSON now includes a 'connector_errors' section listing any
    failures encountered during the run — PKE outages, book matching API
    failures, synthesis failures. Same pattern as Scout's feed_errors and
    Editor's chunk_errors.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")

    json_path = output_dir / f"connected_{date_str}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "connect_date": date_str,
                "connect_timestamp": datetime.now(timezone.utc).isoformat(),
                "connector_errors": asdict(errors),
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

    # Errors accumulator — populated throughout the run, surfaced at the end
    errors = ConnectorErrors()

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

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # ---------------------------------------------------------------------------
    # Step 1: Find PKE corpus connections for each item
    # Per-item PKE errors are aggregated rather than logged individually —
    # if PKE is down, every item will hit the same root cause and 10 lines
    # of identical errors is just noise.
    # ---------------------------------------------------------------------------
    connected_items: list[ConnectedItem] = []
    if not skip_pke:
        errors.pke_total_items = len(editor_items)

    for item in editor_items:
        connections: list[Connection] = []

        if not skip_pke:
            pke_conns, pke_err = find_pke_connections(item, pke_url)
            if pke_err:
                # First failure: record the error as the sample. Don't log
                # per-item; the summary at the end will say "N/M items failed"
                # with this representative message.
                errors.pke_items_failed += 1
                if not errors.pke_sample_error:
                    errors.pke_sample_error = pke_err
            else:
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
        if synthesis.get("error"):
            errors.synthesis_error = synthesis["error"]
        apply_synthesis(connected_items, synthesis)

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
        if book_results.get("error"):
            errors.book_matching_error = book_results["error"]
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

    # Surface errors loudly at the end — same pattern as Scout and Editor.
    # These are not warnings; they mean parts of the run silently produced
    # less than they should have.
    if errors.has_errors():
        logger.warning("=== Connector Errors ===")
        if errors.pke_items_failed:
            logger.warning(
                f"  ✗ PKE queries failed for {errors.pke_items_failed}/"
                f"{errors.pke_total_items} items — sample error: {errors.pke_sample_error}"
            )
        if errors.book_matching_error:
            logger.warning(f"  ✗ Book matching API failed: {errors.book_matching_error}")
        if errors.synthesis_error:
            logger.warning(f"  ✗ PKE synthesis API failed: {errors.synthesis_error}")
    else:
        logger.info("=== Connector clean — no errors ===")

    if dry_run:
        logger.info("Dry run — no output written")
        return connected_items

    if output_dir is None:
        output_dir = Path(__file__).parent / "output" / "connected"
    write_connector_output(connected_items, errors, output_dir)

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
