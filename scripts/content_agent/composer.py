"""
Content Curation Agent — Composer

Takes the Connector's annotated items and produces two outputs:

  Daily drop   — a scannable markdown brief (3-5 items, 5 minutes)
  Weekly synthesis — a deeper brief with patterns, strongest connections,
                     and pillar-level observations (runs Sunday)

Output lands in the Obsidian vault as markdown files.

Usage:
    python -m scripts.content_agent.composer --daily
    python -m scripts.content_agent.composer --weekly
    python -m scripts.content_agent.composer --daily --vault-path /path/to/vault
"""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error tracking
# ---------------------------------------------------------------------------


@dataclass
class ComposerErrors:
    """
    Errors encountered during composition.

    Tracked in structured form so the bat file can surface them in Pipeline
    Status, same pattern as Scout/Editor/Connector. Each field is populated
    only when the relevant failure occurred.
    """

    # Daily failures
    no_connector_output: bool = False
    empty_connector_input: bool = False  # Connector ran but produced 0 items
    daily_vault_write_error: str = ""
    daily_output_write_error: str = ""
    malformed_items_skipped: int = 0  # Items missing title or url

    # Weekly failures
    no_weekly_items: bool = False
    weekly_api_error: str = ""
    weekly_empty_response: bool = False
    weekly_vault_write_error: str = ""
    weekly_output_write_error: str = ""

    def has_errors(self) -> bool:
        return any([
            self.no_connector_output,
            self.empty_connector_input,
            self.daily_vault_write_error,
            self.daily_output_write_error,
            self.malformed_items_skipped > 0,
            self.no_weekly_items,
            self.weekly_api_error,
            self.weekly_empty_response,
            self.weekly_vault_write_error,
            self.weekly_output_write_error,
        ])

    def has_fatal_errors(self) -> bool:
        """
        True if any error means no usable output was produced.
        Fatal errors should cause a non-zero exit code so the bat file knows.
        """
        return any([
            self.no_connector_output,
            self.empty_connector_input,
            self.daily_vault_write_error,
            self.daily_output_write_error,
            self.no_weekly_items,
            self.weekly_api_error,
            self.weekly_empty_response,
        ])


def _write_errors_file(errors: ComposerErrors, output_dir: Path) -> None:
    """
    Write errors to a JSON file the bat file can read.

    Lives alongside the brief outputs. The bat file reads this to surface
    Composer errors to Pipeline Status, same pattern as the other agents.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    errors_path = output_dir / f"composer_errors_{date_str}.json"
    with open(errors_path, "w", encoding="utf-8") as f:
        json.dump(asdict(errors), f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Daily drop
# ---------------------------------------------------------------------------


def compose_daily(
    input_path: Optional[Path] = None,
    vault_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    errors: Optional[ComposerErrors] = None,
) -> Path:
    """
    Compose the daily drop from Connector output.

    Returns the output file path on success, or Path() on failure.
    The errors parameter is populated with structured failure info if
    anything goes wrong — the caller is expected to surface these.
    """
    if errors is None:
        errors = ComposerErrors()

    # Load connected items
    if input_path is None:
        connected_dir = Path(__file__).parent / "output" / "connected"
        json_files = sorted(connected_dir.glob("connected_*.json"), reverse=True)
        if not json_files:
            logger.error("No Connector output found.")
            errors.no_connector_output = True
            return Path()
        input_path = json_files[0]

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])

    # Empty input is a silent failure mode — Connector ran but produced nothing.
    # This is what bit us yesterday: empty editor_filtered → empty connected →
    # header-only daily drop with no real content. Treat it as fatal.
    if not items:
        logger.error(
            "Connector output has 0 items — upstream pipeline likely failed. "
            "Daily drop would be empty."
        )
        errors.empty_connector_input = True
        return Path()

    date_str = datetime.now().strftime("%Y-%m-%d")
    day_name = datetime.now().strftime("%A")

    # Validate items — skip malformed ones rather than producing a corrupted brief
    valid_items = []
    for item in items:
        if not item.get("title") or not item.get("url"):
            errors.malformed_items_skipped += 1
            continue
        valid_items.append(item)

    if errors.malformed_items_skipped:
        logger.warning(
            f"Skipped {errors.malformed_items_skipped} malformed items "
            f"(missing title or url)"
        )

    # If validation removed everything, treat as fatal — same as empty input
    if not valid_items:
        logger.error("All items were malformed — daily drop would be empty.")
        errors.empty_connector_input = True
        return Path()

    # Build daily drop markdown
    lines = []
    lines.append(f"# Daily Drop — {day_name}, {date_str}\n")

    with_conn = [i for i in valid_items if i.get("connections")]
    without_conn = [i for i in valid_items if not i.get("connections")]

    strength_order = {"strong": 0, "solid": 1, "worth_noting": 2}
    with_conn.sort(key=lambda x: strength_order.get(x.get("strength", ""), 9))
    without_conn.sort(key=lambda x: strength_order.get(x.get("strength", ""), 9))

    if with_conn:
        lines.append("## With Connections\n")
        for item in with_conn:
            lines.extend(_format_daily_item(item))

    if without_conn:
        lines.append("## Curation\n")
        for item in without_conn:
            lines.extend(_format_daily_item(item))

    content = "\n".join(lines)

    # Write to Obsidian vault if path provided.
    # Wrap in try/except — a vault write failure should not look like success.
    if vault_path:
        try:
            brief_dir = vault_path / "Content Briefs"
            brief_dir.mkdir(parents=True, exist_ok=True)
            vault_file = brief_dir / f"Daily Drop {date_str}.md"
            with open(vault_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Daily drop written to vault: {vault_file}")
        except OSError as e:
            error_msg = str(e)
            logger.error(f"Failed to write daily drop to vault: {error_msg}")
            errors.daily_vault_write_error = error_msg

    # Also write to agent output directory
    if output_dir is None:
        output_dir = Path(__file__).parent / "output" / "briefs"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"daily_drop_{date_str}.md"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Daily drop written: {out_file}")
        return out_file
    except OSError as e:
        error_msg = str(e)
        logger.error(f"Failed to write daily drop to output dir: {error_msg}")
        errors.daily_output_write_error = error_msg
        return Path()


def _format_daily_item(item: dict) -> list[str]:
    """Format a single item for the daily drop."""
    lines = []
    strength_marker = {"strong": "★", "solid": "●", "worth_noting": "○"}.get(
        item.get("strength", ""), "·"
    )
    pub = item.get("published", "")[:10] if item.get("published") else ""
    pillar = item.get("pillar", "")
    cross = item.get("cross_pillar", [])
    pillar_str = pillar
    if cross:
        pillar_str += f" + {', '.join(cross)}"

    lines.append(f"### {strength_marker} {item['title']}\n")
    lines.append(f"*{item.get('source_name', '')} | {pillar_str} | {pub}*\n")
    lines.append(f"{item.get('editor_reason', '')}\n")

    if item.get("summary"):
        lines.append(f"> {item['summary'][:250]}\n")

    for conn in item.get("connections", []):
        conn_source = conn.get("source", "")
        conn_title = conn.get("title", "")
        conn_note = conn.get("relevance_note", "")
        conn_date = conn.get("date", "")

        if conn_source == "pke":
            lines.append(f"**↔ Personal connection:** {conn_note}")
            lines.append(f"*From: {conn_title} ({conn_date})*\n")
        elif conn_source == "books":
            lines.append(f"**↔ Book connection:** {conn_note}")
            lines.append(f"*{conn_title} ({conn_date})*\n")

    lines.append(f"[Read full article]({item.get('url', '')})\n")
    lines.append("---\n")
    return lines


# ---------------------------------------------------------------------------
# Weekly synthesis
# ---------------------------------------------------------------------------

WEEKLY_SYNTHESIS_PROMPT = """You are the Composer agent producing a weekly synthesis
brief for a senior technology leader who writes about AI in banking, intellectual
history, and building real systems.

You have been given the full week's curated content with connections to personal
history and reading.

Produce a weekly synthesis with these sections:

1. WHAT'S ALIVE THIS WEEK (2-3 sentences)
   The dominant theme or tension across this week's content. What is the
   conversation right now?

2. STRONGEST ITEMS (3-5)
   The items worth reading in full. One sentence each on why.

3. SURPRISING CONNECTIONS (0-3)
   Pairings between curated content and personal history or books that
   are genuinely interesting — not forced. If none are surprising, say so.

4. PILLAR HEALTH
   One sentence per pillar on coverage quality this week.
   Flag any pillar that was thin.

5. POST SEED (0-1)
   If any item or connection this week could seed a LinkedIn post in
   the person's voice — practitioner, specific, intellectually curious —
   describe the angle in 2-3 sentences. If nothing is strong enough,
   say "Nothing this week" and don't force it.

Write in a direct, intelligent voice. No filler. No corporate language.
The reader is sharp and has no patience for padding.

Respond in markdown format (not JSON).
"""


def compose_weekly(
    vault_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    errors: Optional[ComposerErrors] = None,
) -> Path:
    """Compose the weekly synthesis from the week's daily outputs."""
    import os
    from dotenv import load_dotenv

    if errors is None:
        errors = ComposerErrors()

    load_dotenv()

    connected_dir = Path(__file__).parent / "output" / "connected"
    filtered_dir = Path(__file__).parent / "output" / "filtered"
    week_items = []
    source_used = None
    today = datetime.now()

    for days_back in range(7):
        date = today - timedelta(days=days_back)
        date_str = date.strftime("%Y-%m-%d")
        json_file = connected_dir / f"connected_{date_str}.json"
        if json_file.exists():
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items", [])
            if items:
                week_items.extend(items)
                if source_used is None:
                    source_used = "connected"

    if not week_items:
        logger.info("No connected items found — falling back to editor-filtered output")
        for days_back in range(7):
            date = today - timedelta(days=days_back)
            date_str = date.strftime("%Y-%m-%d")
            json_file = filtered_dir / f"editor_filtered_{date_str}.json"
            if json_file.exists():
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                items = data.get("items", [])
                if items:
                    week_items.extend(items)
                    if source_used is None:
                        source_used = "filtered"

    if not week_items:
        logger.error(
            "No items found for this week in connected or filtered output. "
            "Check that the daily pipeline (Scout → Editor) is running successfully."
        )
        errors.no_weekly_items = True
        return Path()

    logger.info(f"Weekly synthesis: {len(week_items)} items from {source_used} output")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot generate weekly synthesis")
        errors.weekly_api_error = "ANTHROPIC_API_KEY not set"
        return Path()

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
                "system": WEEKLY_SYNTHESIS_PROMPT,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Here are this week's curated items with connections:\n\n"
                        f"{json.dumps(week_items, indent=2)}",
                    }
                ],
            },
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()

        synthesis_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                synthesis_text += block["text"]

    except (requests.RequestException, json.JSONDecodeError) as e:
        error_msg = str(e)
        logger.error(f"Weekly synthesis API call failed: {error_msg}")
        errors.weekly_api_error = error_msg
        return Path()

    # Empty response — Claude returned no text. Don't write a useless header-only brief.
    if not synthesis_text.strip():
        logger.error("Weekly synthesis API returned empty text — refusing to write empty brief")
        errors.weekly_empty_response = True
        return Path()

    date_str = today.strftime("%Y-%m-%d")
    week_num = today.strftime("%W")
    year = today.strftime("%Y")

    content = f"# Weekly Synthesis — Week {week_num}, {year}\n\n"
    content += f"*Generated: {date_str}*\n"
    content += f"*Items reviewed: {len(week_items)}*\n\n"
    content += synthesis_text

    if vault_path:
        try:
            brief_dir = vault_path / "Content Briefs"
            brief_dir.mkdir(parents=True, exist_ok=True)
            vault_file = brief_dir / f"Weekly Synthesis {year}-W{week_num}.md"
            with open(vault_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Weekly synthesis written to vault: {vault_file}")
        except OSError as e:
            error_msg = str(e)
            logger.error(f"Failed to write weekly synthesis to vault: {error_msg}")
            errors.weekly_vault_write_error = error_msg

    if output_dir is None:
        output_dir = Path(__file__).parent / "output" / "briefs"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"weekly_synthesis_{year}_W{week_num}.md"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Weekly synthesis written: {out_file}")
        return out_file
    except OSError as e:
        error_msg = str(e)
        logger.error(f"Failed to write weekly synthesis to output dir: {error_msg}")
        errors.weekly_output_write_error = error_msg
        return Path()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Content Curation Agent — Composer")
    parser.add_argument("--daily", action="store_true", help="Compose daily drop")
    parser.add_argument("--weekly", action="store_true", help="Compose weekly synthesis")
    parser.add_argument(
        "--vault-path", type=Path, default=None, help="Path to Obsidian vault for output"
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory for briefs")
    parser.add_argument(
        "--input", type=Path, default=None, help="Input file (for daily: connected JSON)"
    )
    args = parser.parse_args()

    if not args.daily and not args.weekly:
        args.daily = True

    # Single errors object collects failures from whichever modes ran
    errors = ComposerErrors()

    if args.daily:
        compose_daily(
            input_path=args.input,
            vault_path=args.vault_path,
            output_dir=args.output_dir,
            errors=errors,
        )

    if args.weekly:
        compose_weekly(
            vault_path=args.vault_path,
            output_dir=args.output_dir,
            errors=errors,
        )

    # Write errors file so the bat can surface to Pipeline Status
    errors_output_dir = args.output_dir or (Path(__file__).parent / "output" / "briefs")
    _write_errors_file(errors, errors_output_dir)

    # Surface errors loudly at the end — same pattern as Scout/Editor/Connector
    if errors.has_errors():
        logger.warning("=== Composer Errors ===")
        if errors.no_connector_output:
            logger.warning("  ✗ No Connector output found — run Connector first")
        if errors.empty_connector_input:
            logger.warning("  ✗ Connector output had 0 valid items — upstream pipeline failed")
        if errors.malformed_items_skipped:
            logger.warning(
                f"  ✗ Skipped {errors.malformed_items_skipped} malformed items "
                f"(missing title or url)"
            )
        if errors.daily_vault_write_error:
            logger.warning(f"  ✗ Daily vault write failed: {errors.daily_vault_write_error}")
        if errors.daily_output_write_error:
            logger.warning(f"  ✗ Daily output write failed: {errors.daily_output_write_error}")
        if errors.no_weekly_items:
            logger.warning("  ✗ Weekly synthesis found no items in past 7 days")
        if errors.weekly_api_error:
            logger.warning(f"  ✗ Weekly synthesis API failed: {errors.weekly_api_error}")
        if errors.weekly_empty_response:
            logger.warning("  ✗ Weekly synthesis API returned empty text")
        if errors.weekly_vault_write_error:
            logger.warning(f"  ✗ Weekly vault write failed: {errors.weekly_vault_write_error}")
        if errors.weekly_output_write_error:
            logger.warning(f"  ✗ Weekly output write failed: {errors.weekly_output_write_error}")
    else:
        logger.info("=== Composer clean — no errors ===")

    # Exit non-zero on fatal errors so the bat file's `if errorlevel 1` check fires.
    # This is the key behavior change: empty briefs or write failures used to look
    # like success because the function returned without raising. Now they don't.
    if errors.has_fatal_errors():
        sys.exit(1)
