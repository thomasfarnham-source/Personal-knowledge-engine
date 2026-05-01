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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Daily drop
# ---------------------------------------------------------------------------


def compose_daily(
    input_path: Optional[Path] = None,
    vault_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """Compose the daily drop from Connector output."""

    # Load connected items
    if input_path is None:
        connected_dir = Path(__file__).parent / "output" / "connected"
        json_files = sorted(connected_dir.glob("connected_*.json"), reverse=True)
        if not json_files:
            logger.error("No Connector output found.")
            return Path()
        input_path = json_files[0]

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    date_str = datetime.now().strftime("%Y-%m-%d")
    day_name = datetime.now().strftime("%A")

    # Build daily drop markdown
    lines = []
    lines.append(f"# Daily Drop — {day_name}, {date_str}\n")

    # Items with connections first, then without
    with_conn = [i for i in items if i.get("connections")]
    without_conn = [i for i in items if not i.get("connections")]

    # Sort each group by strength
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

    # Write to Obsidian vault if path provided
    if vault_path:
        brief_dir = vault_path / "Content Briefs"
        brief_dir.mkdir(parents=True, exist_ok=True)
        vault_file = brief_dir / f"Daily Drop {date_str}.md"
        with open(vault_file, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Daily drop written to vault: {vault_file}")

    # Also write to agent output directory
    if output_dir is None:
        output_dir = Path(__file__).parent / "output" / "briefs"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"daily_drop_{date_str}.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Daily drop written: {out_file}")
    return out_file


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

    # Connections
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


def compose_weekly(vault_path: Optional[Path] = None, output_dir: Optional[Path] = None) -> Path:
    """Compose the weekly synthesis from the week's daily outputs."""
    import os
    from dotenv import load_dotenv
    load_dotenv()

    # Gather the week's items — prefer connected (has PKE/book annotations),
    # fall back to editor-filtered (curation without personal connections).
    # The GitHub Actions daily pipeline skips the Connector (no PKE API in CI),
    # so connected files only exist after local enrichment runs. The weekly
    # synthesis should still work from editor-filtered output alone.
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

    # Fallback: if no connected items, try editor-filtered output
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
        logger.warning(
            "No items found for this week in connected or filtered output. "
            "Check that the daily pipeline (Scout → Editor) is running successfully."
        )
        return Path()

    logger.info(f"Weekly synthesis: {len(week_items)} items from {source_used} output")

    # Call Claude for synthesis
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot generate weekly synthesis")
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
        logger.error(f"Weekly synthesis API call failed: {e}")
        return Path()

    # Build the weekly brief
    date_str = today.strftime("%Y-%m-%d")
    week_num = today.strftime("%W")
    year = today.strftime("%Y")

    content = f"# Weekly Synthesis — Week {week_num}, {year}\n\n"
    content += f"*Generated: {date_str}*\n"
    content += f"*Items reviewed: {len(week_items)}*\n\n"
    content += synthesis_text

    # Write to vault
    if vault_path:
        brief_dir = vault_path / "Content Briefs"
        brief_dir.mkdir(parents=True, exist_ok=True)
        vault_file = brief_dir / f"Weekly Synthesis {year}-W{week_num}.md"
        with open(vault_file, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Weekly synthesis written to vault: {vault_file}")

    # Write to agent output
    if output_dir is None:
        output_dir = Path(__file__).parent / "output" / "briefs"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"weekly_synthesis_{year}_W{week_num}.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Weekly synthesis written: {out_file}")
    return out_file


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
        args.daily = True  # Default to daily

    if args.daily:
        compose_daily(
            input_path=args.input,
            vault_path=args.vault_path,
            output_dir=args.output_dir,
        )

    if args.weekly:
        compose_weekly(
            vault_path=args.vault_path,
            output_dir=args.output_dir,
        )
