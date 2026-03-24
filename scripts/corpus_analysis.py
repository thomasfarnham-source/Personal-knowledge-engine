"""
scripts/corpus_analysis.py

Corpus Analysis Tool — Milestone 9.2

Reads the ingested iMessage corpus from Supabase and produces a structured
analytical report across eight dimensions. Output is a timestamped Markdown
file saved to scripts/corpus_analysis_reports/.

This is the raw material the producer uses to write the Personality Skin
system prompt for the Companion Engine (milestone 9.3). The specifics
extracted here — vocabulary fingerprints, pushback rates, temporal patterns
— are what make the system prompt work. Generic adjectives are worthless.
Specifics extracted from the real corpus are everything.

Usage:
    python scripts/corpus_analysis.py
    python scripts/corpus_analysis.py --thread-type group
    python scripts/corpus_analysis.py --thread-id <id> --no-interpret

Output:
    scripts/corpus_analysis_reports/corpus_analysis_YYYY-MM-DD_HHMMSS.md

The eight dimensions:
    1. Relationship History     — volume over time, gaps, silence periods
    2. Group Dynamics           — starter rates, response rates, burst depth
    3. Individual Profiles      — vocabulary, message length, cadence
    4. Relationship Pairs       — per-pair dynamics, pushback rates
    5. Core Themes              — topic clustering, recurring debates
    6. Emotional Register       — warmth/friction, handling of difficulty
    7. Temporal Patterns        — time of day, day of week, yearly trends
    8. Group Self-Awareness     — in-jokes, how the group talks about itself

Fixes v2 (2026-03-23):
    - Vocabulary fingerprint: lift now compares sender word frequency against
      corpus-wide word frequency rather than document frequency across senders.
      Previous version compared against number of senders who used the word
      (document frequency), which produced lift scores too low to pass the
      threshold — resulting in empty fingerprints. Now uses corpus-wide TF
      comparison which correctly identifies words each sender uses
      disproportionately relative to the group baseline.
    - Burst fetch: paginated to avoid 1000-row Supabase default limit.
      Previous version silently truncated at 1000 bursts.
    - URL stripping: URLs removed from text before tokenizing for themes and
      vocabulary so top words reflect actual content (people, ideas, places)
      rather than URL fragments (https, com, youtu, reflink etc).
    - URL fragment tokens added to stopwords as belt-and-suspenders.
    - Missing year detection: years with zero messages now flagged explicitly
      in the report header as known data gaps.
    - EST conversion: peak hours now reported in both UTC and EST (UTC-5)
      so temporal findings are immediately readable without mental arithmetic.
"""

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import anthropic
from anthropic.types import TextBlock
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).parent / "corpus_analysis_reports"
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Stopwords
#
# Two categories:
#
#   Common English — words too frequent across all senders to be distinctive.
#     These suppress noise in both vocabulary fingerprinting and theme analysis.
#
#   URL fragments — tokens produced by splitting URLs on non-alpha characters.
#     Even with URL stripping, partial tokens like "https", "com", "youtu"
#     can survive. Belt-and-suspenders exclusion here ensures they never
#     appear in fingerprints or theme word lists.
#
# The stopword list is intentionally broad. If a word that carries real signal
# ends up here it can be removed — but false positives from stopword gaps
# are more disruptive to the output than false negatives.
# ---------------------------------------------------------------------------
STOPWORDS = {
    # Common English
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "is",
    "it",
    "he",
    "she",
    "they",
    "we",
    "you",
    "that",
    "this",
    "was",
    "are",
    "be",
    "have",
    "has",
    "had",
    "do",
    "did",
    "will",
    "would",
    "could",
    "should",
    "not",
    "no",
    "so",
    "if",
    "as",
    "from",
    "by",
    "up",
    "out",
    "about",
    "what",
    "which",
    "who",
    "my",
    "your",
    "his",
    "her",
    "its",
    "our",
    "their",
    "me",
    "him",
    "us",
    "them",
    "just",
    "like",
    "get",
    "got",
    "one",
    "can",
    "all",
    "more",
    "when",
    "there",
    "been",
    "into",
    "than",
    "then",
    "now",
    "also",
    "some",
    "how",
    "any",
    "were",
    "said",
    "yes",
    "yeah",
    "ok",
    "okay",
    "lol",
    "haha",
    "too",
    "over",
    "why",
    "right",
    "going",
    "time",
    "good",
    "know",
    "think",
    "well",
    "even",
    "back",
    "see",
    "really",
    "still",
    "much",
    "very",
    "way",
    "make",
    "take",
    "come",
    "here",
    "after",
    "being",
    "same",
    "where",
    "while",
    "again",
    "because",
    "these",
    "those",
    "both",
    "each",
    "few",
    "own",
    "other",
    "such",
    "only",
    "before",
    "off",
    "down",
    "never",
    "always",
    "every",
    "need",
    "want",
    "might",
    "look",
    "first",
    "last",
    "long",
    "great",
    "little",
    "man",
    "things",
    "thing",
    "though",
    "put",
    "end",
    "does",
    "old",
    "new",
    "since",
    "came",
    "let",
    "may",
    "give",
    "use",
    "found",
    "tell",
    "asked",
    "show",
    "around",
    # Contractions — handled by regex but belt-and-suspenders
    "it's",
    "i'm",
    "don't",
    "that's",
    "i've",
    "i'll",
    "we're",
    "they're",
    "you're",
    "he's",
    "she's",
    "we've",
    "they've",
    "can't",
    "won't",
    "didn't",
    "doesn't",
    "isn't",
    "aren't",
    "wasn't",
    "weren't",
    "i'd",
    "im",
    "ive",
    "dont",
    "cant",
    "wont",
    "didnt",
    "doesnt",
    "thats",
    "ill",
    # URL fragments — appear even after URL stripping due to partial tokenization
    "https",
    "http",
    "www",
    "com",
    "html",
    "php",
    "utm",
    "ref",
    "src",
    "feature",
    "share",
    "watch",
    "youtu",
    "youtube",
    "reflink",
    "status",
    "mobilewebshare",
    "dok",
    "shorts",
    "si",
    "fbclid",
    "amp",
}

# ---------------------------------------------------------------------------
# Reaction message prefixes
#
# iMessage reaction notifications show up as standalone messages:
#     "Liked 'some text'"
#     "Laughed at 'some text'"
# These are metadata, not content — excluded from all analysis.
# ---------------------------------------------------------------------------
REACTION_PATTERNS = {
    "Laughed at",
    "Liked",
    "Loved",
    "Disliked",
    "Emphasized",
    "Questioned",
}

# Compiled URL regex — used for both stripping and extraction
URL_RE = re.compile(r"https?://\S+|www\.\S+")


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


def get_supabase_client() -> Any:
    """
    Create and return a Supabase client using environment variables.
    Credentials are read from .env via load_dotenv() at module load time.
    """
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def fetch_messages(
    client: Any,
    thread_type: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch all messages from imessage_messages, optionally filtered by
    thread type or specific thread ID.

    Paginates in batches of 1000 to avoid the Supabase default row limit.
    Without pagination, corpora over 1000 messages are silently truncated —
    the group chat alone has 13,000+ messages.

    Parameters
    ----------
    client       : Supabase client
    thread_type  : "group" | "bilateral" | None (all threads)
    thread_id    : specific thread UUID | None (all threads)

    Returns
    -------
    List of message dicts with fields:
        id, thread_id, sender_name, timestamp, text, message_type, has_text
    """
    # Resolve thread ID filter — either direct or via thread_type lookup
    filter_thread_ids: Optional[List[str]] = None
    if thread_id:
        filter_thread_ids = [thread_id]
    elif thread_type:
        resp = (
            client.table("imessage_threads").select("id").eq("thread_type", thread_type).execute()
        )
        filter_thread_ids = [r["id"] for r in (resp.data or [])]
        if not filter_thread_ids:
            return []

    all_rows: List[Dict[str, Any]] = []
    offset = 0
    batch_size = 1000

    while True:
        query = client.table("imessage_messages").select(
            "id, thread_id, sender_name, timestamp, text, message_type, has_text"
        )
        if filter_thread_ids:
            query = query.in_("thread_id", filter_thread_ids)

        resp = query.range(offset, offset + batch_size - 1).order("timestamp").execute()
        batch = resp.data or []
        all_rows.extend(batch)
        if len(batch) < batch_size:
            break
        offset += batch_size

    return all_rows


def fetch_threads(client: Any) -> List[Dict[str, Any]]:
    """
    Fetch all thread metadata from imessage_threads.
    Used for the report corpus summary and missing year detection.
    """
    resp = client.table("imessage_threads").select("*").execute()
    return resp.data or []


def fetch_bursts(
    client: Any,
    thread_type: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch all bursts from imessage_bursts, optionally filtered.

    Paginates identically to fetch_messages — the group chat has 964
    bursts alone, and with bilateral threads the total exceeds 1279,
    which would be silently truncated without pagination.

    Returns burst dicts with fields needed for Group Dynamics analysis:
        id, thread_id, thread_name, thread_type, burst_index,
        date_start, date_end, participants, dominant_sender, text_combined
    """
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    batch_size = 1000

    while True:
        query = client.table("imessage_bursts").select(
            "id, thread_id, thread_name, thread_type, burst_index, date_start, "
            "date_end, participants, dominant_sender, text_combined"
        )
        if thread_id:
            query = query.eq("thread_id", thread_id)
        elif thread_type:
            query = query.eq("thread_type", thread_type)

        resp = query.range(offset, offset + batch_size - 1).order("date_start").execute()
        batch = resp.data or []
        all_rows.extend(batch)
        if len(batch) < batch_size:
            break
        offset += batch_size

    return all_rows


# ---------------------------------------------------------------------------
# Text processing helpers
# ---------------------------------------------------------------------------


def is_reaction(text: str) -> bool:
    """
    Return True if the message text is an iMessage reaction notification.
    Reactions are metadata — they tell you someone reacted to a message,
    not what they said. Excluded from all content analysis.
    """
    return any(text.startswith(p) for p in REACTION_PATTERNS)


def clean_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter messages to content-bearing messages only.
    Removes:
        - Empty or whitespace-only messages
        - Reaction notifications (Liked, Laughed at, etc.)

    The cleaned list is the basis for all eight analytical dimensions.
    """
    return [m for m in messages if m.get("text", "").strip() and not is_reaction(m["text"].strip())]


def strip_urls(text: str) -> str:
    """
    Remove URLs from text before tokenization.

    Without stripping, URL fragments dominate the top word lists:
    "https", "com", "youtu", "reflink", "mobilewebshare" etc.
    Stripping ensures vocabulary analysis reflects actual human language.

    URLs are extracted separately for domain analysis before stripping —
    see dimension_5_core_themes().
    """
    return URL_RE.sub(" ", text)


def parse_timestamp(ts: str) -> datetime:
    """
    Parse Supabase timestamp strings to timezone-aware datetime objects.

    Supabase returns timestamps in several formats:
        "2023-04-15 20:30:00+00"    — most common
        "2023-04-15T20:30:00Z"      — ISO 8601 with Z suffix

    Both are normalised to "+00:00" for fromisoformat() compatibility.
    All timestamps in imessage_messages are stored as UTC.
    """
    ts = ts.replace("+00", "+00:00")
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def tokenize(text: str) -> List[str]:
    """
    Convert a message string into a list of meaningful content words.

    Process:
        1. Strip URLs (removes https://... patterns before tokenising)
        2. Lowercase
        3. Extract alpha tokens only (regex [a-z']+)
        4. Filter stopwords and short tokens (len > 2)

    The apostrophe in [a-z']+ preserves contractions (it's, don't) as
    single tokens so they can be filtered cleanly by the stopword list.
    Without this they'd split into fragments ("it", "s") that pass the
    length filter but carry no meaning.
    """
    text = strip_urls(text)
    words = re.findall(r"[a-z']+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


# ---------------------------------------------------------------------------
# Dimension 1 — Relationship History
#
# What it measures:
#     The volume and continuity of the relationship over time.
#     When did the conversation begin? When was it most active?
#     What periods went silent, and for how long?
#
# Why it matters for the personality descriptor:
#     The arc of a relationship shapes its register. A group that started
#     strong, went silent for four years, and then reignited has a
#     fundamentally different dynamic than one with steady continuity.
#     The silence periods are as revealing as the active ones.
# ---------------------------------------------------------------------------


def dimension_1_relationship_history(
    messages: List[Dict[str, Any]],
    threads: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Produce volume-over-time statistics including silence period detection.

    Silence periods are consecutive months with zero messages. Single silent
    months are recorded in silent_months_count but not silence_periods —
    only gaps of two or more consecutive months appear in silence_periods,
    as these represent meaningful conversational pauses.

    Missing years are years within the span that have zero messages —
    distinct from silence periods in that they represent full calendar years
    of absence rather than short gaps. These are flagged in the report header.
    """
    if not messages:
        return {}

    clean = clean_messages(messages)

    # Build monthly message counts
    monthly: Counter[str] = Counter()
    for m in clean:
        dt = parse_timestamp(m["timestamp"])
        monthly[dt.strftime("%Y-%m")] += 1

    months = sorted(monthly.keys())
    if not months:
        return {}

    # Build complete month range from first to last active month
    first_year, first_mo = map(int, months[0].split("-"))
    last_year, last_mo = map(int, months[-1].split("-"))

    all_months: List[str] = []
    y, mo = first_year, first_mo
    while (y, mo) <= (last_year, last_mo):
        all_months.append(f"{y:04d}-{mo:02d}")
        mo += 1
        if mo > 12:
            mo = 1
            y += 1

    silent_months = [month for month in all_months if monthly.get(month, 0) == 0]

    # Identify consecutive silence periods (2+ months)
    silence_periods: List[Tuple[str, str]] = []
    if silent_months:
        period_start = silent_months[0]
        prev = silent_months[0]
        for month in silent_months[1:]:
            py, pmo = map(int, prev.split("-"))
            next_exp = f"{py:04d}-{pmo+1:02d}" if pmo < 12 else f"{py+1:04d}-01"
            if month == next_exp:
                # Consecutive — extend the current period
                prev = month
            else:
                # Gap — close the current period and start a new one
                if period_start != prev:
                    silence_periods.append((period_start, prev))
                period_start = month
                prev = month
        # Close the final period
        if period_start != prev:
            silence_periods.append((period_start, prev))

    # Yearly rollup
    yearly: Counter[str] = Counter()
    for m in clean:
        dt = parse_timestamp(m["timestamp"])
        yearly[str(dt.year)] += 1

    # Detect years within the span that have zero messages
    all_years = list(range(first_year, last_year + 1))
    missing_years = [str(y) for y in all_years if str(y) not in yearly]

    peak_month = max(monthly, key=lambda k: monthly[k]) if monthly else None

    return {
        "total_messages": len(clean),
        "date_range": {
            "first": months[0],
            "last": months[-1],
            "span_months": len(all_months),
        },
        "yearly_volume": dict(sorted(yearly.items())),
        "missing_years": missing_years,
        "peak_month": peak_month,
        "peak_month_count": monthly.get(peak_month, 0) if peak_month else 0,
        "silent_months_count": len(silent_months),
        "silence_periods": [{"start": s, "end": e} for s, e in silence_periods],
        "monthly_volume": dict(sorted(monthly.items())),
    }


# ---------------------------------------------------------------------------
# Dimension 2 — Group Dynamics
#
# What it measures:
#     Who drives the conversation. Who responds. Who watches.
#     Starter rates, response patterns, burst depth per person.
#
# Why it matters for the personality descriptor:
#     The engine of a group chat is not evenly distributed. One person
#     typically ignites conversations; others follow, deepen, or observe.
#     Understanding who plays which role — and how consistent those roles
#     are — is foundational to characterising the group's voice.
#
# Key metrics:
#     starter_pct         — what fraction of conversations does each person begin
#     volume_pct          — raw message share
#     avg_burst_depth     — how deep conversations go when each person starts one
#     response_rate_proxy — messages sent relative to opportunities to respond
#                           (volume / (total - own volume))
#                           Patrick's value > 1.0 means he sends more than
#                           there are "turns" available — he's often continuing
#                           conversations into silence
# ---------------------------------------------------------------------------


def dimension_2_group_dynamics(
    messages: List[Dict[str, Any]],
    bursts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute conversation starter rates, volume distribution, and burst depth.

    Burst depth is approximated from text_combined line count rather than
    raw message count. This is accurate enough for comparative analysis
    (who triggers deep vs shallow conversations) without requiring a separate
    message-to-burst join.

    Response rate proxy: sender_messages / (total_messages - sender_messages)
    This captures how actively each person engages with the conversation
    relative to the opportunities created by others. Values > 1.0 indicate
    the sender often continues when no one else responds.
    """
    clean = clean_messages(messages)
    if not clean:
        return {}

    senders = sorted({m["sender_name"] for m in clean})
    volume: Counter[str] = Counter(m["sender_name"] for m in clean)
    total = len(clean)
    total_bursts = len(bursts)

    # Burst starters and depth
    starters: Counter[str] = Counter()
    burst_depth_by_starter: Dict[str, List[int]] = defaultdict(list)
    for burst in bursts:
        dominant = burst.get("dominant_sender", "")
        if dominant:
            starters[dominant] += 1
            text = burst.get("text_combined", "")
            # Approximate message count from non-empty lines in text_combined
            msg_count = len([line for line in text.split("\n") if line.strip()])
            burst_depth_by_starter[dominant].append(msg_count)

    avg_burst_depth = {s: round(sum(d) / len(d), 1) for s, d in burst_depth_by_starter.items() if d}

    # Response rate proxy
    response_rate = {
        s: round(volume[s] / (total - volume[s]), 3) for s in senders if (total - volume[s]) > 0
    }

    return {
        "senders": senders,
        "total_messages": total,
        "total_bursts": total_bursts,
        "volume_per_sender": dict(volume.most_common()),
        "volume_pct": {s: round(volume[s] / total * 100, 1) for s in senders},
        "starter_count": dict(starters.most_common()),
        "starter_pct": {
            s: round(starters[s] / total_bursts * 100, 1) for s in senders if total_bursts > 0
        },
        "avg_burst_depth_when_starting": avg_burst_depth,
        "response_rate_proxy": response_rate,
    }


# ---------------------------------------------------------------------------
# Dimension 3 — Individual Profiles
#
# What it measures:
#     Each person's distinctive verbal signature. How they write.
#     What words they use disproportionately. How long their messages are.
#     When they tend to be active.
#
# Why it matters for the personality descriptor:
#     A composite group voice needs to understand the channels it is mixing.
#     Patrick's vocabulary fingerprint is different from James's. William
#     writes longer messages than anyone else. These are the raw materials
#     for channel characterisation in the Personality Skin.
#
# Vocabulary fingerprint — how it works:
#     For each word a sender uses, we compute a lift score:
#
#         sender_freq  = count in sender's messages / sender's total words
#         corpus_freq  = count in all messages       / corpus total words
#         lift         = sender_freq / corpus_freq
#
#     Lift > 2.0 means the sender uses this word at least twice as often
#     as the group average. Minimum count of 3 to filter hapax legomena.
#     Top 20 by lift score constitute the fingerprint.
#
#     This replaced the previous document-frequency approach (which counted
#     how many senders used the word, then divided by that count) — the
#     prior approach produced lift scores too low to exceed the threshold,
#     resulting in empty fingerprints for all senders.
# ---------------------------------------------------------------------------


def dimension_3_individual_profiles(
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Per-sender vocabulary fingerprint, message length statistics, and cadence.

    All senders share the same corpus_words counter as the baseline for
    lift calculation. This ensures fingerprints are genuinely contrastive —
    a word appearing in every sender's messages at similar rates will have
    lift ≈ 1.0 and not appear in any fingerprint, even if it's frequent.
    Only words that one sender uses markedly more than the group as a whole
    will surface.
    """
    clean = clean_messages(messages)
    if not clean:
        return {}

    senders = sorted({m["sender_name"] for m in clean})

    # Build corpus-wide word frequency — shared baseline for all lift calculations
    # Using Counter[str] so mypy knows the key and value types precisely.
    corpus_words: Counter[str] = Counter()
    sender_words: Dict[str, Counter[str]] = {}

    for sender in senders:
        sender_msgs = [m for m in clean if m["sender_name"] == sender]
        words: List[str] = []
        for m in sender_msgs:
            words.extend(tokenize(m["text"]))
        sender_words[sender] = Counter(words)
        # All sender words contribute to the shared corpus baseline
        corpus_words.update(words)

    total_corpus_words = sum(corpus_words.values())

    profiles: Dict[str, Any] = {}
    for sender in senders:
        sender_msgs = [m for m in clean if m["sender_name"] == sender]
        texts = [m["text"] for m in sender_msgs]

        # Message length on raw text (not stripped) — reflects actual writing style
        lengths = [len(t.split()) for t in texts]

        sw = sender_words[sender]
        total_sender_words = sum(sw.values())

        # Compute lift for each word and select the most distinctive.
        # lift = (word_count_for_sender / sender_total_words)
        #      / (word_count_in_corpus / corpus_total_words)
        # Words with lift >= 2.0 are used at least twice the corpus rate.
        fingerprint: List[Tuple[str, int, float]] = []
        if total_sender_words > 0 and total_corpus_words > 0:
            for word, count in sw.most_common(1000):
                if count < 3:
                    # Too rare to be a reliable fingerprint signal
                    continue
                sender_freq = count / total_sender_words
                corpus_freq = corpus_words[word] / total_corpus_words
                if corpus_freq == 0:
                    continue
                lift_score = sender_freq / corpus_freq
                if lift_score >= 2.0:
                    fingerprint.append((word, count, round(lift_score, 2)))

            # Sort by lift descending — most distinctive words first
            fingerprint.sort(key=lambda x: x[2], reverse=True)
            fingerprint = fingerprint[:20]

        # Peak activity hour
        timestamps = [parse_timestamp(m["timestamp"]) for m in sender_msgs]
        hour_dist: Counter[int] = Counter(dt.hour for dt in timestamps)
        peak_hour_utc = max(hour_dist, key=lambda h: hour_dist[h]) if hour_dist else None

        profiles[sender] = {
            "message_count": len(sender_msgs),
            "avg_message_length_words": (round(sum(lengths) / len(lengths), 1) if lengths else 0),
            "median_message_length_words": (sorted(lengths)[len(lengths) // 2] if lengths else 0),
            "short_message_rate": (
                # Rate of messages 3 words or fewer — signals terse/reactive style
                round(sum(1 for length in lengths if length <= 3) / len(lengths), 2)
                if lengths
                else 0
            ),
            "url_sharing_rate": (
                # Fraction of messages containing a URL — signals link-sharing behaviour
                round(sum(1 for t in texts if "http" in t.lower()) / len(texts), 2)
                if texts
                else 0
            ),
            "peak_hour_utc": peak_hour_utc,
            "peak_hour_est": (peak_hour_utc - 5) % 24 if peak_hour_utc is not None else None,
            "vocabulary_fingerprint": [
                {"word": w, "count": c, "lift": ls} for w, c, ls in fingerprint
            ],
            "total_unique_words": len(sw),
        }

    return {"profiles": profiles}


# ---------------------------------------------------------------------------
# Dimension 4 — Relationship Pairs
#
# What it measures:
#     The bilateral dynamics between every pair of participants.
#     Who exchanges most with whom. Who pushes back on whom.
#     Sample exchanges that illustrate the dynamic.
#
# Why it matters for the personality descriptor:
#     A five-person group has ten distinct bilateral relationships, each
#     with its own character. The Patrick-James dynamic (highest exchange
#     count, 12.6% pushback) is different from the Patrick-Thomas dynamic
#     (second highest, slightly lower pushback). Understanding these
#     bilateral registers is essential for the Personality Skin — the
#     group voice is a synthesis of these relationships, not a homogeneous
#     average.
#
# Pushback detection:
#     A simple keyword scan for words that signal disagreement, challenge,
#     or reframing. The pushback_rate is the fraction of exchanges in which
#     the response contains at least one pushback word. This is a proxy, not
#     a precise sentiment score — but it's sufficient for comparative analysis
#     across pairs and consistent enough for the personality descriptor.
# ---------------------------------------------------------------------------


def dimension_4_relationship_pairs(
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Analyse every sender pair for exchange volume, pushback rate, and
    sample exchanges.

    An "exchange" is defined as two consecutive messages between the same
    pair of senders (ignoring other senders between them). This is a
    conservative definition — it only counts direct back-and-forth, not
    multi-message runs — but it's deterministic and comparable across pairs.

    Sample exchanges are drawn at three points: the earliest, middle, and
    most recent exchange. This gives the producer a sense of how the
    dynamic has evolved over time.
    """
    clean = clean_messages(messages)
    if not clean:
        return {}

    senders = sorted({m["sender_name"] for m in clean})

    # Keywords that signal disagreement, challenge, or reframing
    pushback_words = {
        "but",
        "actually",
        "wrong",
        "disagree",
        "nope",
        "not really",
        "don't think",
        "doubt",
        "though",
        "however",
        "although",
        "wait",
        "hold on",
        "except",
        "unless",
        "rather",
        "instead",
    }

    pairs: Dict[str, Dict[str, Any]] = {}
    for i in range(len(senders)):
        for j in range(i + 1, len(senders)):
            s1, s2 = senders[i], senders[j]

            exchanges: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
            pushbacks = 0

            for idx in range(1, len(clean)):
                prev = clean[idx - 1]
                curr = clean[idx]
                # A valid exchange: consecutive messages from these two senders
                if {prev["sender_name"], curr["sender_name"]} == {s1, s2} and prev[
                    "sender_name"
                ] != curr["sender_name"]:
                    exchanges.append((prev, curr))
                    # Does the response contain a pushback signal?
                    if any(pb in curr["text"].lower() for pb in pushback_words):
                        pushbacks += 1

            if not exchanges:
                continue

            # Sample from start, middle, end of the exchange history
            indices = sorted({0, len(exchanges) // 2, len(exchanges) - 1})
            samples = [
                {
                    "from": exchanges[idx][0]["sender_name"],
                    "text": exchanges[idx][0]["text"][:120],
                    "response_from": exchanges[idx][1]["sender_name"],
                    "response_text": exchanges[idx][1]["text"][:120],
                    "timestamp": exchanges[idx][0]["timestamp"][:10],
                }
                for idx in indices
                if idx < len(exchanges)
            ]

            pairs[f"{s1} \u2194 {s2}"] = {
                "exchange_count": len(exchanges),
                "pushback_rate": round(pushbacks / len(exchanges), 3),
                "pushback_count": pushbacks,
                "sample_exchanges": samples,
            }

    # Sort by exchange count descending — most active pairs first.
    # Cast to int so mypy knows the sort key is comparable.
    sorted_pairs = sorted(
        pairs.items(),
        key=lambda x: int(x[1]["exchange_count"]),
        reverse=True,
    )
    return {"pairs": dict(sorted_pairs)}


# ---------------------------------------------------------------------------
# Dimension 5 — Core Themes
#
# What it measures:
#     What the group actually talks about. The recurring subjects, debates,
#     and external sources they bring into conversation.
#
# Why it matters for the personality descriptor:
#     The Personality Skin system prompt needs to know what the group cares
#     about — the recurring references, the debates without resolution, the
#     external world that enters the thread. Top words and domains are the
#     raw signal; interpreted findings translate them into themes.
#
# URL stripping:
#     Without stripping, top words are entirely URL fragments: "https",
#     "com", "youtu", "reflink", "mobilewebshare". These tell us nothing
#     about what the group discusses. URLs are extracted separately for
#     domain analysis before tokenization strips them.
#
# Domain analysis:
#     Which external sources does the group share most often? WSJ, NYT,
#     YouTube, Deadline — these reveal the group's information diet and
#     cultural frame of reference. Worth naming explicitly in the
#     personality descriptor.
# ---------------------------------------------------------------------------


def dimension_5_core_themes(
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Extract top content words, bigrams, and shared URL domains.

    Two-pass approach:
        1. Extract URLs from raw text before stripping (for domain analysis)
        2. Tokenize URL-stripped text for word and bigram frequency

    This gives us both the content vocabulary and the external source
    distribution without conflating them.
    """
    clean = clean_messages(messages)
    if not clean:
        return {}

    all_words: Counter[str] = Counter()
    all_bigrams: Counter[str] = Counter()
    urls_shared: List[str] = []

    for m in clean:
        text = m["text"]

        # Extract URLs before stripping — max 2 per message to avoid URL-heavy
        # messages dominating the domain count
        urls_shared.extend(re.findall(r"https?://\S+", text)[:2])

        # Tokenize with URL stripping — content words only
        words = tokenize(text)
        all_words.update(words)

        # Bigrams — captures meaningful two-word phrases that single-word
        # analysis misses (e.g., "book club", "wall street")
        for i in range(len(words) - 1):
            all_bigrams[f"{words[i]} {words[i+1]}"] += 1

    # Extract domain from each URL
    domain_counter: Counter[str] = Counter()
    for url in urls_shared:
        match = re.search(r"https?://(?:www\.)?([^/\s]+)", url)
        if match:
            domain_counter[match.group(1)] += 1

    return {
        "top_words": [{"word": w, "count": c} for w, c in all_words.most_common(30)],
        "top_bigrams": [
            {"bigram": b, "count": c} for b, c in all_bigrams.most_common(20) if c >= 3
        ],
        "url_count": len(urls_shared),
        "top_domains": [{"domain": d, "count": c} for d, c in domain_counter.most_common(15)],
        "messages_with_urls_pct": round(
            sum(1 for m in clean if "http" in m["text"].lower()) / len(clean) * 100,
            1,
        ),
    }


# ---------------------------------------------------------------------------
# Dimension 6 — Emotional Register
#
# What it measures:
#     The emotional texture of the conversation. How warm is it? How much
#     friction? How does the group handle difficulty and humour?
#
# Why it matters for the personality descriptor:
#     The Personality Skin needs to capture the group's emotional register,
#     not just its topics. A warmth/friction ratio of 4.7 tells you this
#     is a fundamentally warm group with occasional friction. A difficulty
#     rate of 9.8% tells you hard subjects surface frequently — illness,
#     loss, struggle. These calibrate the tone of generated responses.
#
# Keyword approach:
#     Simple keyword scanning is blunt but consistent. The signal is in
#     the rates and ratios, not the precision of any individual match.
#     Validated against known corpus characteristics (the group is warm,
#     intellectually combative, handles difficulty with humour-first).
#
# Sarcasm note:
#     This group is highly sarcastic. Warmth keywords like "brilliant" and
#     "legend" are frequently deployed ironically. The warmth/friction ratio
#     likely overstates genuine warmth and understates friction as a result.
#     The rates are useful for comparison across senders; the absolute values
#     should be interpreted with the sarcasm register in mind.
# ---------------------------------------------------------------------------


def dimension_6_emotional_register(
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute warmth, friction, humour, and difficulty rates per sender
    and for the group as a whole.

    Rates are fractions of all messages containing at least one signal word.
    Per-sender counts allow comparison: Patrick generates more warmth signals
    (absolute) simply because he writes more — the rates normalise this.
    """
    clean = clean_messages(messages)
    if not clean:
        return {}

    warmth_words = {
        "love",
        "great",
        "amazing",
        "brilliant",
        "legend",
        "class",
        "nice",
        "good",
        "well done",
        "proud",
        "miss",
        "thanks",
        "thank",
        "congrats",
        "happy",
        "wonderful",
        "delighted",
        "glad",
        "fantastic",
        "beautiful",
        "sweet",
        "kind",
        "generous",
        "thoughtful",
    }
    friction_words = {
        "wrong",
        "stupid",
        "idiot",
        "rubbish",
        "terrible",
        "awful",
        "hate",
        "worst",
        "disagree",
        "nonsense",
        "ridiculous",
        "absurd",
        "annoying",
        "boring",
        "useless",
        "pathetic",
    }
    humour_signals = {
        # Explicit laughter markers and Irish/British humour vocabulary
        "haha",
        "lol",
        "\U0001f602",
        "\U0001f923",
        "\U0001f605",
        "hilarious",
        "funny",
        "jokes",
        "gas",
        "craic",
        "classic",
        "legend",
        "brilliant",
        "priceless",
    }
    difficulty_words = {
        # Topics that signal the group is navigating something hard
        "sorry",
        "tough",
        "hard",
        "difficult",
        "struggling",
        "worried",
        "anxious",
        "stress",
        "sick",
        "ill",
        "cancer",
        "hospital",
        "died",
        "death",
        "funeral",
        "grief",
        "sad",
        "upset",
        "problem",
        "trouble",
    }

    warmth_count = friction_count = humour_count = difficulty_count = 0
    per_sender_warmth: Counter[str] = Counter()
    per_sender_humour: Counter[str] = Counter()

    for m in clean:
        tl = m["text"].lower()
        s = m["sender_name"]
        if any(w in tl for w in warmth_words):
            warmth_count += 1
            per_sender_warmth[s] += 1
        if any(w in tl for w in friction_words):
            friction_count += 1
        if any(w in tl for w in humour_signals):
            humour_count += 1
            per_sender_humour[s] += 1
        if any(w in tl for w in difficulty_words):
            difficulty_count += 1

    total = len(clean)
    return {
        "warmth_rate": round(warmth_count / total, 3),
        "friction_rate": round(friction_count / total, 3),
        "warmth_friction_ratio": round(warmth_count / max(friction_count, 1), 1),
        "humour_rate": round(humour_count / total, 3),
        "difficulty_rate": round(difficulty_count / total, 3),
        "warmth_by_sender": dict(per_sender_warmth.most_common()),
        "humour_by_sender": dict(per_sender_humour.most_common()),
    }


# ---------------------------------------------------------------------------
# Dimension 7 — Temporal Patterns
#
# What it measures:
#     When the group is active. Time of day, day of week, month of year,
#     and how volume has changed across years.
#
# Why it matters for the personality descriptor:
#     A group that peaks at 3pm EST on weekdays has a different rhythm than
#     one that peaks on Saturday evenings. The temporal pattern is part of
#     the group's character — when they show up, how often, and whether
#     that has changed over time.
#
# UTC vs EST:
#     All timestamps are stored as UTC. The group is based in the US Eastern
#     timezone (UTC-5). Peak hour UTC 20 = 3pm EST. Peak hour UTC 8-9 =
#     3-4am EST — which would indicate night owls or international members,
#     neither of which applies here. The morning UTC cluster (6-9) maps to
#     1-4am EST, suggesting those messages come from European time zones
#     or are timestamps with timezone handling anomalies — worth flagging
#     in interpreted findings.
# ---------------------------------------------------------------------------


def dimension_7_temporal_patterns(
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute time-of-day, day-of-week, monthly, and yearly message distributions.

    All hours reported in both UTC and EST (UTC-5) to avoid requiring
    mental arithmetic when reading the report. The "period" buckets
    (morning, afternoon, evening, night) use UTC boundaries — the labels
    note this so readers can adjust expectations accordingly.
    """
    clean = clean_messages(messages)
    if not clean:
        return {}

    hours: Counter[int] = Counter()
    days: Counter[str] = Counter()
    years: Counter[str] = Counter()
    months_of_year: Counter[int] = Counter()
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    for m in clean:
        dt = parse_timestamp(m["timestamp"])
        hours[dt.hour] += 1
        days[day_names[dt.weekday()]] += 1
        years[str(dt.year)] += 1
        months_of_year[dt.month] += 1

    peak_hour_utc = max(hours, key=lambda h: hours[h])

    return {
        "peak_hour_utc": peak_hour_utc,
        "peak_hour_est": (peak_hour_utc - 5) % 24,
        "peak_hour_count": hours[peak_hour_utc],
        "timezone_note": "All timestamps stored as UTC. EST = UTC-5.",
        "hour_distribution_utc": dict(sorted(hours.items())),
        "peak_day": max(days, key=lambda d: days[d]),
        "quietest_day": min(days, key=lambda d: days[d]),
        "day_distribution": {d: days[d] for d in day_names},
        "period_distribution_utc": {
            "morning_6_11": sum(hours[h] for h in range(6, 12)),
            "afternoon_12_17": sum(hours[h] for h in range(12, 18)),
            "evening_18_23": sum(hours[h] for h in range(18, 24)),
            "night_0_5": sum(hours[h] for h in range(0, 6)),
        },
        "yearly_volume": dict(sorted(years.items())),
        "month_of_year_distribution": {str(m): months_of_year[m] for m in range(1, 13)},
    }


# ---------------------------------------------------------------------------
# Dimension 8 — Group Self-Awareness
#
# What it measures:
#     How the group talks about itself. References to group members by name.
#     Self-referential language about the group as an entity.
#
# Why it matters for the personality descriptor:
#     A group with high self-awareness — that names itself, references its
#     own history, talks about its members in the third person — has a
#     different relational texture than one that is purely task-focused.
#     The group's relationship to its own identity is part of its voice.
#
# Name mention asymmetry:
#     Patrick and James mention Chris by name more than anyone else (60 and
#     57 times respectively). Chris mentions almost no one by name. This
#     pattern — being talked about more than you talk — is a signal about
#     Chris's role in the group: he is present, observed, and referenced,
#     but operates at a remove from the direct interpersonal naming dynamic.
# ---------------------------------------------------------------------------


def dimension_8_group_self_awareness(
    messages: List[Dict[str, Any]],
    senders: List[str],
) -> Dict[str, Any]:
    """
    Measure name-mention patterns and self-referential group language.

    Name mentions: for each sender, how often do they reference other
    participants by first name? This reveals attention direction —
    who is talked about, who is addressed, who is referenced.

    Self-referential phrases: messages that reference the group as an entity
    ("we should", "book club", "you guys", "the lads") indicate the group's
    awareness of itself as a collective. These are the moments where the
    group's self-model is visible in the text.
    """
    clean = clean_messages(messages)
    if not clean:
        return {}

    # Build first-name lookup from full sender names
    first_names = {s.strip().split()[0].lower(): s for s in senders if s.strip()}
    name_mentions: Dict[str, Counter[str]] = {s: Counter() for s in senders}

    for m in clean:
        tl = m["text"].lower()
        speaker = m["sender_name"]
        for fname, full_name in first_names.items():
            # Only count mentions of *other* people (not self-reference)
            if fname in tl and full_name != speaker:
                name_mentions[speaker][full_name] += tl.count(fname)

    # Phrases that signal the group talking about itself as a collective
    group_self_ref = [
        "book club",
        "the group",
        "us lot",
        "you guys",
        "you lot",
        "the lads",
        "the boys",
        "we should",
        "we need",
        "we must",
        "remember when",
        "back in",
        "that time",
        "the day we",
    ]

    self_ref_messages: List[Dict[str, str]] = []
    for m in clean:
        tl = m["text"].lower()
        for phrase in group_self_ref:
            if phrase in tl:
                self_ref_messages.append(
                    {
                        "sender": m["sender_name"],
                        "text": m["text"][:150],
                        "timestamp": m["timestamp"][:10],
                        "phrase": phrase,
                    }
                )
                break  # One match per message is enough

    # Sample across the full time range (not just recent messages)
    step = max(1, len(self_ref_messages) // 8)
    samples = self_ref_messages[::step][:8]

    return {
        "name_mentions_by_sender": {
            s: dict(c.most_common()) for s, c in name_mentions.items() if c
        },
        "self_referential_message_count": len(self_ref_messages),
        "self_referential_samples": samples,
    }


# ---------------------------------------------------------------------------
# Claude API — interpreted findings
#
# Each dimension's statistics are passed to Claude with a prompt that
# frames the task: produce 3-5 sentences of plain-language findings
# grounded in the actual numbers, useful for characterising the group's
# voice in the Personality Skin system prompt.
#
# The interpretation pass is the expensive step — 8 API calls, each with
# ~500 tokens of statistics. The --no-interpret flag skips this for fast
# iteration on the statistical output.
# ---------------------------------------------------------------------------


def interpret_dimension(
    dimension_name: str,
    stats: Dict[str, Any],
    context: str,
    client: anthropic.Anthropic,
) -> str:
    """
    Generate plain-language interpretation of one dimension's statistics.

    The prompt is deliberately constrained:
        - 3-5 sentences only (prevents verbose summaries)
        - Must use actual numbers from the data (prevents generic output)
        - No bullet points (ensures flowing prose suitable for the descriptor)
        - UTC hours converted to EST in the output

    Returns the model's response text stripped of leading/trailing whitespace.
    """
    prompt = f"""You are helping analyse a real iMessage group chat corpus to build
a personality descriptor for an AI companion system.

Context: {context}

Dimension: {dimension_name}

Statistics:
{json.dumps(stats, indent=2, default=str)}

Write 3-5 sentences of interpreted findings for this dimension. Be specific —
use the actual numbers, names, and patterns from the data. Avoid generic
observations. Focus on what is distinctive, surprising, or useful for
characterising this group's voice and dynamic. Do not use bullet points.
Write in plain prose. Where hours are given in UTC, convert to EST (UTC-5)
for readability."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    # content[0] is always a TextBlock for standard non-tool responses
    block = message.content[0]
    assert isinstance(block, TextBlock)
    return block.text.strip()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    dimensions: Dict[str, Dict[str, Any]],
    interpreted: Dict[str, str],
    threads: List[Dict[str, Any]],
    run_timestamp: str,
    missing_years: List[str],
) -> str:
    """
    Assemble the full Markdown report from statistics and interpreted findings.

    Structure per dimension:
        ## Dimension N — Name
        ### Interpreted Findings   (if interpretation was run)
        [prose paragraphs]
        ### Statistics
        [JSON block]

    The interpreted findings come first so the report reads naturally as a
    document — statistics support the findings rather than leading them.

    Missing years are flagged in the corpus header as a known data gap,
    not buried in Dimension 1 statistics where they might be missed.
    """
    thread_summary = "\n".join(
        f"- {t['thread_name']} ({t['thread_type']}, {t['message_count']} messages)" for t in threads
    )

    lines = [
        "# PKE Corpus Analysis Report",
        "",
        f"Generated: {run_timestamp}",
        "",
        "## Corpus",
        "",
        thread_summary,
        "",
    ]

    if missing_years:
        lines += [
            f"**Data gaps:** No messages recorded for: {', '.join(missing_years)}. "
            "Conversation likely moved to bilateral threads or a different platform "
            "during these periods. This is a known corpus limitation — absence of "
            "messages in these years does not mean absence of relationship.",
            "",
        ]

    lines += ["---", ""]

    dim_titles = {
        "dimension_1": "Dimension 1 \u2014 Relationship History",
        "dimension_2": "Dimension 2 \u2014 Group Dynamics",
        "dimension_3": "Dimension 3 \u2014 Individual Profiles",
        "dimension_4": "Dimension 4 \u2014 Relationship Pairs",
        "dimension_5": "Dimension 5 \u2014 Core Themes",
        "dimension_6": "Dimension 6 \u2014 Emotional Register",
        "dimension_7": "Dimension 7 \u2014 Temporal Patterns",
        "dimension_8": "Dimension 8 \u2014 Group Self-Awareness",
    }

    for key, title in dim_titles.items():
        stats = dimensions.get(key, {})
        interp = interpreted.get(key, "")

        lines += [f"## {title}", ""]

        if interp:
            lines += ["### Interpreted Findings", "", interp, ""]

        lines += [
            "### Statistics",
            "",
            "```json",
            json.dumps(stats, indent=2, default=str),
            "```",
            "",
            "---",
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "PKE Corpus Analysis Tool — produces an 8-dimension report "
            "from the ingested iMessage corpus."
        )
    )
    parser.add_argument(
        "--thread-type",
        choices=["group", "bilateral"],
        default=None,
        help="Filter to a specific thread type. Default: all threads.",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Filter to a specific thread UUID. Takes precedence over --thread-type.",
    )
    parser.add_argument(
        "--no-interpret",
        action="store_true",
        help=(
            "Skip Claude API interpretation pass. Produces statistics only — "
            "fast and free. Use for iterating on statistical output before "
            "running the full interpretation pass."
        ),
    )
    args = parser.parse_args()

    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    print(f"PKE Corpus Analysis v2 — {run_timestamp}")
    print("Connecting to Supabase...")

    supabase = get_supabase_client()

    print("Fetching threads...")
    threads = fetch_threads(supabase)

    print("Fetching messages...")
    messages = fetch_messages(
        supabase,
        thread_type=args.thread_type,
        thread_id=args.thread_id,
    )
    print(f"  {len(messages)} messages fetched")

    print("Fetching bursts...")
    bursts = fetch_bursts(
        supabase,
        thread_type=args.thread_type,
        thread_id=args.thread_id,
    )
    print(f"  {len(bursts)} bursts fetched")

    senders = sorted({m["sender_name"] for m in messages if m.get("sender_name")})

    print("Running dimension 1 — Relationship History...")
    d1 = dimension_1_relationship_history(messages, threads)
    print("Running dimension 2 — Group Dynamics...")
    d2 = dimension_2_group_dynamics(messages, bursts)
    print("Running dimension 3 — Individual Profiles...")
    d3 = dimension_3_individual_profiles(messages)
    print("Running dimension 4 — Relationship Pairs...")
    d4 = dimension_4_relationship_pairs(messages)
    print("Running dimension 5 — Core Themes...")
    d5 = dimension_5_core_themes(messages)
    print("Running dimension 6 — Emotional Register...")
    d6 = dimension_6_emotional_register(messages)
    print("Running dimension 7 — Temporal Patterns...")
    d7 = dimension_7_temporal_patterns(messages)
    print("Running dimension 8 — Group Self-Awareness...")
    d8 = dimension_8_group_self_awareness(messages, senders)

    dimensions = {
        "dimension_1": d1,
        "dimension_2": d2,
        "dimension_3": d3,
        "dimension_4": d4,
        "dimension_5": d5,
        "dimension_6": d6,
        "dimension_7": d7,
        "dimension_8": d8,
    }

    interpreted: Dict[str, str] = {}
    if not args.no_interpret:
        print("Generating interpreted findings via Claude API...")
        claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        context = (
            f"Group chat among {len(senders)} people: {', '.join(senders)}. "
            f"Spanning {d1.get('date_range', {}).get('first', '?')} to "
            f"{d1.get('date_range', {}).get('last', '?')}. "
            f"Total messages analysed: {len(messages)}."
        )

        dim_names = {
            "dimension_1": "Relationship History",
            "dimension_2": "Group Dynamics",
            "dimension_3": "Individual Profiles",
            "dimension_4": "Relationship Pairs",
            "dimension_5": "Core Themes",
            "dimension_6": "Emotional Register",
            "dimension_7": "Temporal Patterns",
            "dimension_8": "Group Self-Awareness",
        }

        for key, name in dim_names.items():
            print(f"  Interpreting {name}...")
            try:
                interpreted[key] = interpret_dimension(name, dimensions[key], context, claude)
            except Exception as e:
                print(f"  Warning: interpretation failed for {name}: {e}")
                interpreted[key] = ""

    missing_years = d1.get("missing_years", [])
    report = generate_report(dimensions, interpreted, threads, run_timestamp, missing_years)

    output_path = OUTPUT_DIR / f"corpus_analysis_{run_timestamp}.md"
    output_path.write_text(report, encoding="utf-8")

    print(f"\nReport saved to: {output_path}")
    print("\nSummary:")
    print(f"  Messages analysed: {len(messages)}")
    print(f"  Bursts analysed:   {len(bursts)}")
    print(f"  Senders:           {', '.join(senders)}")
    if missing_years:
        print(f"  Missing years:     {', '.join(missing_years)}")
    print(f"  Report:            {output_path.name}")


if __name__ == "__main__":
    main()
