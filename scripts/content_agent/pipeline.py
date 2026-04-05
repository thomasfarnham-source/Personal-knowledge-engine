"""
Content Curation Agent — Pipeline Orchestrator

Runs the full agent chain: Scout → Editor → Connector → Composer

Daily run:  python -m scripts.content_agent.pipeline --daily
Weekly run: python -m scripts.content_agent.pipeline --weekly
Full run:   python -m scripts.content_agent.pipeline --daily --weekly

The pipeline is sequential. Each agent's output is the next agent's input.
If any stage fails, the pipeline stops and reports which stage failed.

Configuration:
    NEWSAPI_KEY          — in .env, for Scout NewsAPI queries
    ANTHROPIC_API_KEY    — in .env, for Editor and Connector Claude calls
    PKE Retrieval API    — must be running at localhost:8000 for Connector
    Obsidian vault path  — set via --vault-path for Composer output
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# Import agent modules
from scripts.content_agent.scout import run_scout
from scripts.content_agent.editor import run_editor
from scripts.content_agent.connector import run_connector
from scripts.content_agent.composer import compose_daily, compose_weekly

logger = logging.getLogger(__name__)


def run_daily_pipeline(
    vault_path: Path | None = None,
    pke_url: str = "http://localhost:8000",
    skip_pke: bool = False,
    skip_books: bool = False,
) -> bool:
    """Run the full daily pipeline."""

    logger.info("=" * 60)
    logger.info("CONTENT CURATION AGENT — DAILY PIPELINE")
    logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    # Stage 1: Scout
    logger.info("\n--- STAGE 1: SCOUT ---")
    try:
        scout_items = run_scout()
        if not scout_items:
            logger.warning("Scout returned no items. Pipeline stopping.")
            return False
        logger.info(f"Scout complete: {len(scout_items)} items")
    except Exception as e:
        logger.error(f"Scout failed: {e}")
        return False

    # Stage 2: Editor
    logger.info("\n--- STAGE 2: EDITOR ---")
    try:
        editor_items, report = run_editor()
        if not editor_items:
            logger.warning("Editor filtered everything. Pipeline stopping.")
            logger.info(f"Editor report: {report.notes}")
            return False
        logger.info(f"Editor complete: {report.items_surviving} items survived")
    except Exception as e:
        logger.error(f"Editor failed: {e}")
        return False

    # Stage 3: Connector
    logger.info("\n--- STAGE 3: CONNECTOR ---")
    try:
        connected_items = run_connector(
            pke_url=pke_url,
            skip_pke=skip_pke,
            skip_books=skip_books,
        )
        with_connections = sum(1 for i in connected_items if i.connections)
        logger.info(
            f"Connector complete: {with_connections}/{len(connected_items)} "
            f"items have connections"
        )
    except Exception as e:
        logger.error(f"Connector failed: {e}")
        return False

    # Stage 4: Composer (daily)
    logger.info("\n--- STAGE 4: COMPOSER (daily) ---")
    try:
        output_path = compose_daily(vault_path=vault_path)
        if output_path:
            logger.info(f"Daily drop composed: {output_path}")
        else:
            logger.warning("Composer produced no output")
            return False
    except Exception as e:
        logger.error(f"Composer failed: {e}")
        return False

    logger.info("\n" + "=" * 60)
    logger.info("DAILY PIPELINE COMPLETE")
    logger.info("=" * 60)
    return True


def run_weekly_pipeline(vault_path: Path | None = None) -> bool:
    """Run the weekly synthesis."""

    logger.info("=" * 60)
    logger.info("CONTENT CURATION AGENT — WEEKLY SYNTHESIS")
    logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    try:
        output_path = compose_weekly(vault_path=vault_path)
        if output_path:
            logger.info(f"Weekly synthesis complete: {output_path}")
            return True
        else:
            logger.warning("Weekly synthesis produced no output")
            return False
    except Exception as e:
        logger.error(f"Weekly synthesis failed: {e}")
        return False


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Content Curation Agent — Pipeline")
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Run full daily pipeline (Scout → Editor → Connector → Composer)",
    )
    parser.add_argument(
        "--weekly", action="store_true", help="Run weekly synthesis from accumulated daily output"
    )
    parser.add_argument(
        "--vault-path", type=Path, default=None, help="Obsidian vault path for output delivery"
    )
    parser.add_argument("--pke-url", default="http://localhost:8000", help="PKE Retrieval API URL")
    parser.add_argument("--skip-pke", action="store_true", help="Skip PKE corpus connections")
    parser.add_argument("--skip-books", action="store_true", help="Skip book database connections")
    args = parser.parse_args()

    if not args.daily and not args.weekly:
        args.daily = True  # Default to daily

    success = True

    if args.daily:
        success = run_daily_pipeline(
            vault_path=args.vault_path,
            pke_url=args.pke_url,
            skip_pke=args.skip_pke,
            skip_books=args.skip_books,
        )

    if args.weekly and success:
        success = run_weekly_pipeline(vault_path=args.vault_path)

    sys.exit(0 if success else 1)
