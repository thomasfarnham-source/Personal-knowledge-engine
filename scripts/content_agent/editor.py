"""
Content Curation Agent — Editor

Takes the Scout's raw feed and applies editorial judgment using the
mandate document. Filters items down to the strongest 7-10 for the
daily drop.

The Editor also monitors Scout performance — tracking kill rates
per source and pillar coverage gaps.

Usage:
    python -m scripts.content_agent.editor
    python -m scripts.content_agent.editor --input path/to/scout_raw.json
    python -m scripts.content_agent.editor --dry-run
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
class EditorItem:
    """A Scout item that survived editorial filtering."""

    title: str
    url: str
    source_name: str
    pillar: str
    published: Optional[str]
    summary: Optional[str]
    origin: str
    item_hash: str
    editor_reason: str  # Why this item survived the filter
    cross_pillar: list[str]  # Other pillars this item touches
    strength: str  # "strong" | "solid" | "worth_noting"


@dataclass
class ChunkError:
    """A chunk of items that failed to be processed by Claude."""

    chunk_index: int   # 0-based chunk number
    item_count: int    # How many items were in the chunk (now silently lost)
    error: str         # Human-readable error description


@dataclass
class EditorReport:
    """Scout performance monitoring."""

    scan_date: str
    items_submitted: int
    items_surviving: int
    kill_rate: float
    kills_by_source: dict  # source_name -> kill count
    pillar_coverage: dict  # pillar -> surviving count
    notes: list[str]  # Editor observations for Producer
    chunk_errors: list[dict]  # Chunks that failed — serialized ChunkError dicts


# ---------------------------------------------------------------------------
# Editorial filtering via Claude API
# ---------------------------------------------------------------------------

EDITOR_SYSTEM_PROMPT = """You are the Editor agent in a content curation system.
Your job is to apply editorial judgment to a raw feed of articles and select
the strongest items for a daily brief.

You are filtering for a specific person: a senior technology leader (SVP) at
a major bank, who builds AI systems hands-on, reads widely in philosophy and
intellectual history, and is developing an external voice as a practitioner
who operates at the intersection of enterprise technology, humanities thinking,
and AI implementation.

MANDATE (follow strictly):

PILLAR 1 — THE PRACTITIONER
Keep: AI implementation in regulated finance, enterprise risk tech, LLM
operationalization in production, AI governance/auditability, regulatory
guidance on AI, DevOps/ServiceNow applied to AI workflows, leadership
through AI transformation, practitioner voices (people who built or led).
Kill: vendor marketing, consultant frameworks, vague transformation claims,
anything written without having built or led something.

PILLAR 2 — THE READER
Keep: intellectual history engaging with AI, philosophy of mind/epistemology/
ethics intersecting with LLMs, literary criticism on AI and creativity,
serious book reviews, historical parallels to AI developments.
Kill: pop science AI takes, shallow philosophical framing, "robots taking jobs."

PILLAR 3 — THE BUILDER
Keep: AI-assisted development workflows, agentic system design, vector
databases/embeddings/RAG, real project experiences, open source AI tools,
research announcements with practical implications.
Kill: tutorials, beginner guides, hype predictions, listicles.

CROSS-PILLAR BONUS: Items touching 2-3 pillars are especially valuable.

For each item in the feed, decide: KEEP or KILL.
For KEEP items, provide:
- reason: one sentence on why this survived (be specific)
- cross_pillar: list of other pillars it touches beyond its primary
- strength: "strong" (exceptional), "solid" (good), or "worth_noting" (marginal but interesting)

Respond ONLY with valid JSON. No preamble, no markdown backticks.
Format:
{
  "decisions": [
    {
      "item_hash": "abc123...",
      "decision": "KEEP" or "KILL",
      "reason": "...",
      "cross_pillar": ["reader"],
      "strength": "strong"
    }
  ],
  "editor_notes": ["Any observations about source quality or coverage gaps"]
}
"""

# How many Scout items to send per Claude API call.
# 152 items in one shot was hitting the 120s timeout.
# At ~25 items per chunk, each call takes ~30-40s — safe margin under the 300s limit.
CHUNK_SIZE = 25


def filter_with_claude_chunk(items: list[dict], api_key: str, chunk_index: int) -> dict:
    """
    Send a single chunk of items to Claude for editorial filtering.

    Returns a decisions dict in the same shape as the original single-call version,
    so apply_decisions() downstream needs no changes. On failure, returns an
    empty-decisions dict with an 'error' field set so the caller can detect
    and track the failure rather than silently dropping items.
    """
    items_for_review = []
    for item in items:
        items_for_review.append(
            {
                "item_hash": item["item_hash"],
                "title": item["title"],
                "source_name": item["source_name"],
                "pillar": item["pillar"],
                "summary": (item.get("summary") or "")[:300],
            }
        )

    user_message = (
        f"Here are {len(items_for_review)} items from today's Scout scan (batch {chunk_index + 1}). "
        f"Apply the mandate and mark each KEEP or KILL. "
        f"Target across all batches: 5-8 total items for the daily brief — be selective.\n\n"
        f"{json.dumps(items_for_review, indent=2)}"
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
                "system": EDITOR_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=300,
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

    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        # Log the failure and return an empty-decisions shape with an 'error' field.
        # The 'error' field is the signal to the caller that this chunk failed —
        # without it, the caller can't distinguish "Claude decided to KILL everything"
        # from "the API call failed entirely". Items from a failed chunk would be
        # treated as KILLed silently, which is the bug we're fixing.
        error_msg = str(e)
        logger.error(f"Claude API call failed (chunk {chunk_index + 1}): {error_msg}")
        return {
            "decisions": [],
            "editor_notes": [f"API error on chunk {chunk_index + 1}: {error_msg}"],
            "error": error_msg,  # Signal to caller that this chunk failed
        }


def filter_with_claude(items: list[dict], api_key: str) -> dict:
    """
    Orchestrate chunked editorial filtering across the full Scout feed.

    Splits items into CHUNK_SIZE batches, calls Claude once per batch,
    then merges all decisions into a single dict. Now also tracks which
    chunks failed so the caller can surface them and know how many items
    were silently dropped.
    """
    chunks = [items[i:i + CHUNK_SIZE] for i in range(0, len(items), CHUNK_SIZE)]
    logger.info(f"Splitting {len(items)} items into {len(chunks)} chunks of ~{CHUNK_SIZE}")

    all_decisions = []
    all_notes = []
    chunk_errors: list[ChunkError] = []

    for i, chunk in enumerate(chunks):
        logger.info(f"Processing chunk {i + 1}/{len(chunks)} ({len(chunk)} items)...")
        result = filter_with_claude_chunk(chunk, api_key, i)
        all_decisions.extend(result.get("decisions", []))
        all_notes.extend(result.get("editor_notes", []))

        # If the chunk returned an 'error' field, capture it as a structured
        # ChunkError so the caller can warn about the silent item loss.
        if result.get("error"):
            chunk_errors.append(ChunkError(
                chunk_index=i,
                item_count=len(chunk),
                error=result["error"],
            ))

    return {
        "decisions": all_decisions,
        "editor_notes": all_notes,
        "chunk_errors": chunk_errors,
    }


# ---------------------------------------------------------------------------
# Apply decisions to Scout items
# ---------------------------------------------------------------------------


def apply_decisions(
    scout_items: list[dict], decisions: dict
) -> tuple[list[EditorItem], EditorReport]:
    """Merge Claude's decisions with Scout items."""

    decision_map = {d["item_hash"]: d for d in decisions.get("decisions", [])}

    surviving = []
    kills_by_source: dict[str, int] = {}
    pillar_counts: dict[str, int] = {}

    for item in scout_items:
        decision = decision_map.get(item["item_hash"])

        if decision and decision.get("decision") == "KEEP":
            editor_item = EditorItem(
                title=item["title"],
                url=item["url"],
                source_name=item["source_name"],
                pillar=item["pillar"],
                published=item.get("published"),
                summary=item.get("summary"),
                origin=item["origin"],
                item_hash=item["item_hash"],
                editor_reason=decision.get("reason", ""),
                cross_pillar=decision.get("cross_pillar", []),
                strength=decision.get("strength", "solid"),
            )
            surviving.append(editor_item)
            pillar_counts[item["pillar"]] = pillar_counts.get(item["pillar"], 0) + 1
        else:
            source = item["source_name"]
            kills_by_source[source] = kills_by_source.get(source, 0) + 1

    kill_rate = 1.0 - (len(surviving) / len(scout_items)) if scout_items else 0.0

    # Serialize ChunkError dataclasses as dicts for the report (JSON-safe)
    chunk_errors = [asdict(ce) for ce in decisions.get("chunk_errors", [])]

    report = EditorReport(
        scan_date=datetime.now().strftime("%Y-%m-%d"),
        items_submitted=len(scout_items),
        items_surviving=len(surviving),
        kill_rate=round(kill_rate, 2),
        kills_by_source=kills_by_source,
        pillar_coverage=pillar_counts,
        notes=decisions.get("editor_notes", []),
        chunk_errors=chunk_errors,
    )

    return surviving, report


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_editor_output(items: list[EditorItem], report: EditorReport, output_dir: Path) -> Path:
    """Write filtered items and editor report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")

    # JSON (for Connector agent)
    json_path = output_dir / f"editor_filtered_{date_str}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "filter_date": date_str,
                "filter_timestamp": datetime.now(timezone.utc).isoformat(),
                "items": [asdict(item) for item in items],
                "report": asdict(report),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    # Markdown (human-readable daily drop)
    md_path = output_dir / f"daily_drop_{date_str}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Daily Drop — {date_str}\n\n")
        f.write(
            f"{report.items_surviving} items from {report.items_submitted} scanned "
            f"(kill rate: {report.kill_rate:.0%})\n\n"
        )

        # Surface chunk errors at the top of the markdown — same pattern as Scout
        if report.chunk_errors:
            f.write(f"## ⚠️ Editor Chunk Failures ({len(report.chunk_errors)})\n\n")
            for ce in report.chunk_errors:
                f.write(
                    f"- Chunk {ce['chunk_index'] + 1}: "
                    f"{ce['item_count']} items lost — {ce['error']}\n"
                )
            f.write("\n")

        strength_order = {"strong": 0, "solid": 1, "worth_noting": 2}
        sorted_items = sorted(items, key=lambda x: strength_order.get(x.strength, 9))

        for item in sorted_items:
            strength_marker = {"strong": "★", "solid": "●", "worth_noting": "○"}.get(
                item.strength, "·"
            )
            pub = item.published[:10] if item.published else ""
            cross = f" | also: {', '.join(item.cross_pillar)}" if item.cross_pillar else ""

            f.write(f"{strength_marker} **{item.title}**\n")
            f.write(f"{item.source_name} | {item.pillar}{cross} | {pub}\n")
            f.write(f"_{item.editor_reason}_\n")
            if item.summary:
                f.write(f"\n{item.summary[:200]}\n")
            f.write(f"\n[Read]({item.url})\n\n---\n\n")

        if report.notes:
            f.write("## Editor Notes\n\n")
            for note in report.notes:
                f.write(f"- {note}\n")

    logger.info(f"Editor output written: {json_path} and {md_path}")
    return json_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_editor(
    input_path: Optional[Path] = None, output_dir: Optional[Path] = None, dry_run: bool = False
) -> tuple[list[EditorItem], EditorReport]:
    """Run the Editor filter on Scout output."""
    import os

    load_dotenv()
    if input_path is None:
        raw_dir = Path(__file__).parent / "output" / "raw"
        json_files = sorted(raw_dir.glob("scout_raw_*.json"), reverse=True)
        if not json_files:
            logger.error("No Scout output found. Run the Scout first.")
            return [], EditorReport(
                scan_date=datetime.now().strftime("%Y-%m-%d"),
                items_submitted=0,
                items_surviving=0,
                kill_rate=0,
                kills_by_source={},
                pillar_coverage={},
                notes=["No Scout output found"],
                chunk_errors=[],
            )
        input_path = json_files[0]

    logger.info(f"Loading Scout output: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        scout_data = json.load(f)

    scout_items = scout_data.get("items", [])
    logger.info(f"Scout items to review: {len(scout_items)}")

    if not scout_items:
        logger.warning("Empty Scout feed — nothing to filter")
        return [], EditorReport(
            scan_date=datetime.now().strftime("%Y-%m-%d"),
            items_submitted=0,
            items_surviving=0,
            kill_rate=0,
            kills_by_source={},
            pillar_coverage={},
            notes=["Empty feed"],
            chunk_errors=[],
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        return [], EditorReport(
            scan_date=datetime.now().strftime("%Y-%m-%d"),
            items_submitted=len(scout_items),
            items_surviving=0,
            kill_rate=1.0,
            kills_by_source={},
            pillar_coverage={},
            notes=["ANTHROPIC_API_KEY not set — cannot filter"],
            chunk_errors=[],
        )

    logger.info("Sending to Claude for editorial filtering...")
    decisions = filter_with_claude(scout_items, api_key)

    # Post-merge trim: when each chunk independently decides KEEP/KILL with a
    # "5-8 total" instruction, the model is still somewhat generous per batch.
    # If we ended up with more than 12 survivors across all chunks, cut down to
    # the top 10 by strength before passing to apply_decisions().
    kept = [d for d in decisions.get("decisions", []) if d.get("decision") == "KEEP"]
    original_kept_count = len(kept)
    if original_kept_count > 12:
        strength_order = {"strong": 0, "solid": 1, "worth_noting": 2}
        kept.sort(key=lambda x: strength_order.get(x.get("strength", "worth_noting"), 9))
        kept = kept[:10]
        kept_hashes = {d["item_hash"] for d in kept}
        decisions["decisions"] = [
            d if d["item_hash"] in kept_hashes or d.get("decision") == "KILL"
            else {**d, "decision": "KILL", "reason": "trimmed by post-merge strength sort"}
            for d in decisions["decisions"]
        ]
        # Fixed log message: was misleading before — said "from X surviving chunks"
        # but X was the post-slice count, not the original count.
        logger.info(
            f"Post-merge trim: reduced {original_kept_count} keeps to top 10 by strength"
        )

    surviving, report = apply_decisions(scout_items, decisions)

    logger.info(
        f"=== Editor Complete: {report.items_surviving} survived "
        f"from {report.items_submitted} (kill rate: {report.kill_rate:.0%}) ==="
    )
    logger.info(f"  Pillar coverage: {report.pillar_coverage}")

    # Surface chunk errors loudly at the end — same pattern as Scout.
    # These are not warnings; they mean items were silently dropped from filtering.
    if report.chunk_errors:
        total_lost = sum(ce["item_count"] for ce in report.chunk_errors)
        logger.warning(
            f"=== Editor Chunk Failures: {len(report.chunk_errors)} chunk(s) failed, "
            f"{total_lost} items silently dropped ==="
        )
        for ce in report.chunk_errors:
            logger.warning(
                f"  ✗ Chunk {ce['chunk_index'] + 1}: "
                f"{ce['item_count']} items — {ce['error']}"
            )

    if report.notes:
        for note in report.notes:
            logger.info(f"  Editor note: {note}")

    if dry_run:
        logger.info("Dry run — no output written")
        return surviving, report

    if output_dir is None:
        output_dir = Path(__file__).parent / "output" / "filtered"
    write_editor_output(surviving, report, output_dir)

    return surviving, report


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Content Curation Agent — Editor")
    parser.add_argument("--input", type=Path, default=None, help="Path to Scout raw feed JSON")
    parser.add_argument(
        "--output-dir", type=Path, default=None, help="Output directory for filtered feed"
    )
    parser.add_argument("--dry-run", action="store_true", help="Filter but don't write output")
    args = parser.parse_args()

    run_editor(input_path=args.input, output_dir=args.output_dir, dry_run=args.dry_run)
