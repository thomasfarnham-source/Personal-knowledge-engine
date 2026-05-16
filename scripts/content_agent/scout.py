"""
Content Curation Agent — Scout

Scans RSS feeds and NewsAPI for content relevant to the three pillars
defined in MANDATE.md. Produces a raw feed of items for the Editor
to filter.

The Scout applies no editorial judgment beyond basic relevance filtering.
Its job is coverage, not taste.

Usage:
    python -m scripts.content_agent.scout
    python -m scripts.content_agent.scout --output-dir path/to/output
    python -m scripts.content_agent.scout --dry-run
"""

import json
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

import feedparser
import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ScoutItem:
    """A single item found by the Scout."""

    title: str
    url: str
    source_name: str
    pillar: str
    published: Optional[str]  # ISO timestamp or None
    summary: Optional[str]
    origin: str  # "rss" or "newsapi"
    item_hash: str = ""  # SHA256 of URL for dedup

    def __post_init__(self) -> None:
        if not self.item_hash:
            self.item_hash = hashlib.sha256(self.url.encode()).hexdigest()[:16]


@dataclass
class FeedError:
    """A feed that failed to scan."""

    name: str
    url: str
    pillar: str
    origin: str  # "rss" or "newsapi"
    error: str  # Human-readable error description


# ---------------------------------------------------------------------------
# RSS scanner
# ---------------------------------------------------------------------------


def scan_rss_feeds(
    sources: dict, max_age_days: int = 7, max_items_per_feed: int = 20
) -> tuple[list[ScoutItem], list[FeedError]]:
    """
    Scan all RSS feeds defined in sources.json.

    Returns both the items found and a list of FeedErrors for any feed
    that failed to scan. Errors are collected rather than swallowed so
    the caller can surface them in the output and logs.
    """
    items = []
    errors: list[FeedError] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    for pillar, feeds in sources.get("rss_feeds", {}).items():
        for feed_config in feeds:
            name = feed_config["name"]
            url = feed_config["url"]
            logger.info(f"Scanning RSS: {name} ({pillar})")

            try:
                feed = feedparser.parse(url)

                # feedparser sets bozo=True for malformed feeds but may still
                # return entries. Only treat it as an error if there are no entries.
                if feed.bozo and not feed.entries:
                    error_msg = str(feed.bozo_exception)
                    logger.warning(f"Feed error for {name}: {error_msg}")
                    errors.append(
                        FeedError(
                            name=name,
                            url=url,
                            pillar=pillar,
                            origin="rss",
                            error=error_msg,
                        )
                    )
                    continue

                count = 0
                for entry in feed.entries[:max_items_per_feed]:
                    published = _parse_feed_date(entry)
                    if published and published < cutoff:
                        continue

                    item = ScoutItem(
                        title=entry.get("title", "").strip(),
                        url=entry.get("link", "").strip(),
                        source_name=name,
                        pillar=pillar,
                        published=published.isoformat() if published else None,
                        summary=_clean_summary(entry.get("summary", "")),
                        origin="rss",
                    )

                    if item.title and item.url:
                        items.append(item)
                        count += 1

                logger.info(f"  → {count} items from {name}")

            except Exception as e:
                # Catch-all for unexpected errors (SSL, network, parse failures)
                error_msg = str(e)
                logger.error(f"Failed to scan {name}: {error_msg}")
                errors.append(
                    FeedError(
                        name=name,
                        url=url,
                        pillar=pillar,
                        origin="rss",
                        error=error_msg,
                    )
                )

    return items, errors


def _parse_feed_date(entry: dict) -> Optional[datetime]:
    """Extract publication date from a feed entry."""
    for field_name in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field_name)
        if parsed:
            try:
                from time import mktime

                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except (ValueError, OverflowError):
                continue
    return None


def _clean_summary(raw: str) -> str:
    """Strip HTML tags from RSS summary content."""
    import re

    text = re.sub(r"<[^>]+>", "", raw)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    return text.strip()[:500]  # Cap summary length


# ---------------------------------------------------------------------------
# NewsAPI scanner
# ---------------------------------------------------------------------------


def scan_newsapi(
    sources: dict, api_key: str, max_age_days: int = 7
) -> tuple[list[ScoutItem], list[FeedError]]:
    """
    Scan NewsAPI with queries defined in sources.json.

    Returns both the items found and a list of FeedErrors for any query
    that failed, so callers can surface them alongside RSS errors.
    """
    items: list[ScoutItem] = []
    errors: list[FeedError] = []
    newsapi_config = sources.get("newsapi", {})

    if not newsapi_config.get("enabled", False):
        logger.info("NewsAPI disabled in sources.json")
        return items, errors

    if not api_key:
        logger.warning("NEWSAPI_KEY not set — skipping NewsAPI scan")
        return items, errors

    base_url = "https://newsapi.org/v2/everything"
    from_date = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")

    for query_config in newsapi_config.get("queries", []):
        query_name = query_config["name"]
        logger.info(f"Scanning NewsAPI: {query_name} ({query_config['pillar']})")

        try:
            params = {
                "q": query_config["q"],
                "from": from_date,
                "language": newsapi_config.get("language", "en"),
                "sortBy": newsapi_config.get("sort_by", "relevancy"),
                "pageSize": newsapi_config.get("page_size", 10),
                "apiKey": api_key,
            }

            response = requests.get(base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "ok":
                error_msg = data.get("message", "Unknown NewsAPI error")
                logger.warning(f"NewsAPI error for {query_name}: {error_msg}")
                errors.append(
                    FeedError(
                        name=query_name,
                        url=base_url,
                        pillar=query_config["pillar"],
                        origin="newsapi",
                        error=error_msg,
                    )
                )
                continue

            count = 0
            for article in data.get("articles", []):
                item = ScoutItem(
                    title=article.get("title", "").strip(),
                    url=article.get("url", "").strip(),
                    source_name=article.get("source", {}).get("name", "Unknown"),
                    pillar=query_config["pillar"],
                    published=article.get("publishedAt"),
                    summary=(
                        article.get("description", "")[:500] if article.get("description") else None
                    ),
                    origin="newsapi",
                )

                if item.title and item.url and item.title != "[Removed]":
                    items.append(item)
                    count += 1

            logger.info(f"  → {count} items from query '{query_name}'")

        except requests.RequestException as e:
            error_msg = str(e)
            logger.error(f"NewsAPI request failed for {query_name}: {error_msg}")
            errors.append(
                FeedError(
                    name=query_name,
                    url=base_url,
                    pillar=query_config["pillar"],
                    origin="newsapi",
                    error=error_msg,
                )
            )

    return items, errors


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def deduplicate(items: list[ScoutItem]) -> list[ScoutItem]:
    """Remove duplicate items by URL hash."""
    seen = set()
    unique = []
    for item in items:
        if item.item_hash not in seen:
            seen.add(item.item_hash)
            unique.append(item)
    return unique


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_raw_feed(items: list[ScoutItem], errors: list[FeedError], output_dir: Path) -> Path:
    """
    Write the raw feed as a JSON file and a readable markdown file.

    The JSON now includes a feed_errors section listing every source that
    failed to scan, so downstream agents and humans can see what went dark.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")

    # JSON (machine-readable, for Editor agent)
    json_path = output_dir / f"scout_raw_{date_str}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "scan_date": date_str,
                "scan_timestamp": datetime.now(timezone.utc).isoformat(),
                "item_count": len(items),
                "feed_error_count": len(errors),
                # Feed errors listed explicitly so nothing is silent
                "feed_errors": [asdict(e) for e in errors],
                "items": [asdict(item) for item in items],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    # Markdown (human-readable, for Producer review)
    md_path = output_dir / f"scout_raw_{date_str}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Scout Raw Feed — {date_str}\n\n")
        f.write(f"Items found: {len(items)}\n\n")

        # Surface feed errors at the top of the markdown so they're impossible to miss
        if errors:
            f.write(f"## ⚠️ Feed Errors ({len(errors)})\n\n")
            for e in errors:
                f.write(f"- **{e.name}** ({e.pillar}, {e.origin}): {e.error}\n")
            f.write("\n")

        by_pillar: dict[str, list[ScoutItem]] = {}
        for item in items:
            by_pillar.setdefault(item.pillar, []).append(item)

        for pillar in ("practitioner", "reader", "builder"):
            pillar_items = by_pillar.get(pillar, [])
            f.write(f"## {pillar.title()} ({len(pillar_items)} items)\n\n")
            for item in pillar_items:
                pub = item.published[:10] if item.published else "no date"
                f.write(f"### {item.title}\n")
                f.write(f"Source: {item.source_name} | {pub} | via {item.origin}\n")
                if item.summary:
                    f.write(f"\n{item.summary}\n")
                f.write(f"\n[Link]({item.url})\n\n---\n\n")

    logger.info(f"Raw feed written: {json_path} and {md_path}")
    return json_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_scout(output_dir: Optional[Path] = None, dry_run: bool = False) -> list[ScoutItem]:
    """Run the full Scout scan."""
    import os

    load_dotenv()

    # Load sources
    sources_path = Path(__file__).parent / "sources.json"
    with open(sources_path, "r", encoding="utf-8") as f:
        sources = json.load(f)

    settings = sources.get("scan_settings", {})
    max_age = settings.get("max_age_days", 7)
    max_rss = settings.get("rss_max_items_per_feed", 20)

    # Scan RSS
    logger.info("=== RSS Scan ===")
    rss_items, rss_errors = scan_rss_feeds(
        sources, max_age_days=max_age, max_items_per_feed=max_rss
    )

    # Scan NewsAPI
    logger.info("=== NewsAPI Scan ===")
    api_key = os.environ.get("NEWSAPI_KEY", "")
    newsapi_items, newsapi_errors = scan_newsapi(sources, api_key, max_age_days=max_age)

    # Combine items and errors
    all_items = deduplicate(rss_items + newsapi_items)
    all_errors = rss_errors + newsapi_errors

    logger.info(
        f"=== Scout Complete: {len(all_items)} unique items "
        f"(RSS: {len(rss_items)}, NewsAPI: {len(newsapi_items)}) ==="
    )

    # Pillar breakdown
    by_pillar: dict[str, list[ScoutItem]] = {}
    for item in all_items:
        by_pillar.setdefault(item.pillar, []).append(item)
    for pillar, items in sorted(by_pillar.items()):
        logger.info(f"  {pillar}: {len(items)} items")

    # Surface feed errors loudly — these are not warnings, they are blind spots
    if all_errors:
        logger.warning(f"=== Feed Errors: {len(all_errors)} source(s) failed to scan ===")
        for e in all_errors:
            logger.warning(f"  ✗ {e.name} ({e.pillar}, {e.origin}): {e.error}")
    else:
        logger.info("=== All feeds scanned successfully ===")

    if dry_run:
        logger.info("Dry run — no output written")
        return all_items

    # Write output
    if output_dir is None:
        output_dir = Path(__file__).parent / "output" / "raw"
    write_raw_feed(all_items, all_errors, output_dir)

    return all_items


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Content Curation Agent — Scout")
    parser.add_argument(
        "--output-dir", type=Path, default=None, help="Output directory for raw feed files"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Scan sources but don't write output"
    )
    args = parser.parse_args()

    run_scout(output_dir=args.output_dir, dry_run=args.dry_run)
