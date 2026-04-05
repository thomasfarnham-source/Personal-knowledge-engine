# CURRENT_TASK.md

Last updated: 2026-03-27

---

## Active Branch: feat/9.13-yahoo-mail-parser

---

## Previous Milestones — Completed

### 9.1 — iMessage Parser ✅ (2026-03-22)

What shipped:
- Parser (imessage_parser.py) — 50 tests passing
- Ingestor (imessage_ingestor.py) — 27 tests passing
- CLI (ingest_imessage.py) — Typer, registered as pke ingest-imessage
- Schema migration (add_imessage_tables.sql) — run against Supabase
- SupabaseClient extended (upsert_rows, delete_where, fetch_unembedded_bursts,
  update_burst_embedding)
- All four CSV threads ingested into Supabase:
  - Group chat: 13,560 messages, 964 bursts
  - Patrick bilateral: 963 messages, 276 bursts
  - Patrick + James + William: 42 messages, 38 bursts
  - Patrick + William + Glenn: 1 message, 1 burst
  - Total: 14,566 messages, 1,279 bursts
- embed_chunks.py extended to backfill iMessage burst embeddings
- Embedding backfill run: 1,279 chunks + 1,279 bursts embedded
- match_chunks RPC updated for all source types (LEFT JOINs + COALESCE)
- iMessage bursts verified surfacing in Obsidian Reflections panel
- 464 tests passing
- PR created and merged

---

### 9.2 — Corpus Analysis Tool ✅ (2026-03-23)

What shipped:
- scripts/corpus_analysis.py — eight-dimension analysis tool
- scripts/corpus_analysis_reports/ — timestamped report outputs
- Interpretation pass via Claude API (--no-interpret flag for fast iteration)
- Vocabulary fingerprint using corpus-wide TF lift comparison
- Burst and message fetch paginated (fixes silent 1000-row truncation)
- URLs stripped before tokenizing

The eight dimensions:
1. Relationship History     — volume over time, silence periods, missing years
2. Group Dynamics           — who starts conversations, who responds, who watches
3. Individual Profiles      — each sender's vocabulary fingerprint and writing style
4. Relationship Pairs       — per-pair exchange volume, pushback rates, sample exchanges
5. Core Themes              — what the group actually talks about and shares externally
6. Emotional Register       — warmth/friction ratio, humour patterns, difficulty handling
7. Temporal Patterns        — when the group is active by hour, day, month, and year
8. Group Self-Awareness     — how the group talks about itself and its own history

Key findings from first full run (group chat, 13,602 messages):
- Patrick starts 71% of conversations, 50% of all messages
- Group is binary: either highly active or completely silent
- Peak month January 2024 (1,185 msgs); near-silence 2019-2021 and 2025
- WSJ/NYT primary external sources; YouTube dominant for music and video
- Internal vocabulary: Major Mango, Billy Broadway, Tim Dillon, Uncle Joe
- Warmth/friction ratio 4.7 — likely overstated, group is highly sarcastic
- William writes least but longest messages (16 words avg vs 8-10 for others)
- Patrick's vocabulary fingerprint is empty — his words ARE the corpus baseline

Deferred:
- Diff report on subsequent runs (noted in code, not yet implemented)
- Tests for analysis functions (standalone script, not in test suite)

---

### Obsidian Plugin Improvements ✅ (2026-03-26/27)

Completed outside a feature branch (committed directly to main in plugin repo).
All changes are live and verified working.

What shipped:
- Passage truncation increased from 200 → 1,500 characters
- Reflection suppression — sliding window (50 queries), state lives in
  PKEInsightPlugin not PKEInsightView (survives view recreation)
- Similarity score tooltip on hover over passage text
- "Why?" explanation button — on-demand Claude Haiku call (~$0.002/click),
  renders one-line semantic explanation inline below passage
- Debounce intervals increased: immediate=3s, moment=15s, stop=30s
- Anthropic API key field added to plugin settings
- Auto-copy build step — esbuild.config.mjs now copies main.js and
  styles.css to Obsidian vault after every production build
- Plugin test harness scaffolded by Copilot (tests/ directory)

Key architectural decision:
  Suppression state belongs in PKEInsightPlugin (plugin layer), not
  PKEInsightView (view layer). Obsidian can recreate ItemView instances
  on workspace events — state in the view resets to zero. Plugin layer
  state persists for the full plugin lifetime.

Pending (deferred):
- HTML stripping re-ingest — archetype_a.py updated with strip_html(),
  but Joplin corpus not yet re-ingested. Run when convenient:
    pke ingest run
    python -m pke.cli.embed_chunks

---


---

## Current Milestone: 9.13 — Yahoo Mail Parser

Status: IN PROGRESS
Branch: feat/9.13-yahoo-mail-parser

### What this milestone builds

A parser that ingests personal email correspondence from Yahoo Mail
into the PKE knowledge base. Follows the same pluggable parser pattern
as the Joplin and iMessage parsers:
    source files → parser → ParsedNote contract → ingest pipeline

This milestone also introduces two architectural changes:
  1. retrieval_units table — a unified retrieval surface that all
     content sources write to. Replaces the pattern of extending
     match_chunks with LEFT JOINs for each new source.
  2. contacts + contact_identifiers tables — the Entity Layer seed,
     providing cross-channel identity resolution.


### Design decisions made (2026-03-27)

**Scope — contact-centric, not folder-centric**
Ingest by contact, tracking correspondence to and from specific people.
Not all email — selected correspondents only. Group emails (multiple
recipients) are supported. UI for contact selection deferred to a
later pass — initial pass uses config file or CLI argument to specify
target senders.

**Privacy tier**
Same logic as iMessage bilateral threads (Tier 3 — bilateral/relational).
Applied by default. No new privacy tier needed.

**Export format — IMAP via export server (DECIDED)**

  Yahoo provides two IMAP servers:
    Standard: imap.mail.yahoo.com — caps at 10,000 messages per folder,
              SEARCH results also capped. Not viable for historical corpus.
    Export:   export.imap.mail.yahoo.com — bypasses the 10K limit.
              Confirmed 100,000 messages visible in Inbox. Full history
              back to 2006. Same credentials, same app password.

  IMAP SEARCH is capped on both servers (results capped at ~1,000).
  FETCH by UID has no cap — this is the viable extraction method.

  Yahoo does NOT have a native bulk export feature. MBOX data export
  (login.yahoo.com/account/request-data) was initially recommended
  but Yahoo's own help pages confirm no export feature exists.

  The MBOX export approach was rejected in favour of IMAP because:
    - Full Inbox is 100K+ messages, most are commercial noise
    - Only ~5-10 contacts are in scope for first ingestion pass
    - IMAP allows selective download by contact
    - No need to download and store the full mailbox

**Two-pass extraction strategy (DECIDED)**

  Pass 1 — Header scan (complete)
    Connect to export.imap.mail.yahoo.com
    FETCH headers only for ALL messages in ALL folders by UID
    Store in local SQLite index: yahoo_index.db
    Headers include: From, To, CC, Date, Subject, Message-ID,
    In-Reply-To, References
    Size: ~1-2KB per message. 187,320 headers indexed in 42 minutes.
    Result: complete index of all emails for querying and contact analysis.

  Pass 2 — Selective download (not yet built)
    Query the header index for messages involving target contacts
    FETCH full RFC822 bodies for matched messages only by UID
    Save to MBOX files per contact or per folder in pke-data/yahoo-mail/
    Expected volume: ~1,500-2,500 emails instead of 187,000+

  Pass 3 — Parse and ingest (follows existing pipeline pattern)
    MBOX files → yahoo_mail_parser.py → ParsedNote contract → orchestrator
    Same pattern as Joplin and iMessage. MBOX files are the source of truth.

**Data storage architecture (DECIDED)**

  Header index: local SQLite file (working/temporary data)
    Path: C:\Users\thoma\Documents\dev\pke-data\yahoo-mail\yahoo_index.db
    187,320 rows, all folders scanned. Queryable for contact analysis.
    Disposable — can be rebuilt from IMAP at any time.

  Contacts + identifiers: Supabase (permanent, cross-channel)
    This is the seed of the Entity Layer (Section 17 of ARCHITECTURE.md).
    Not Yahoo-specific — will serve as the cross-channel identity registry
    for iMessage participants, email contacts, and future sources.
    Schema design pending — next action after selective downloader.

  Parsed email content: Supabase via existing ingestion pipeline
    Same tables and flow as Joplin and iMessage content.

**Deduplication**
Group emails (Thomas + others on same thread) must not produce duplicate
records. Deduplication keyed on Message-ID header (unique per email).

**HTML email bodies**
Most Yahoo Mail is HTML. Same strip_html() approach as Joplin archetype
chunkers — strip tags, decode entities, preserve prose content.

**Yahoo app password**
Generated via login.yahoo.com/account/security → External connections
→ Create app password. Requires two-step verification enabled.
Stored in .env as YAHOO_EMAIL and YAHOO_APP_PASSWORD.

### Header index findings (2026-03-27)

Full scan completed: 187,320 headers across 41 folders.
Date range: 2006-09-04 to 2026-03-28 (20 years of email).

Folder breakdown (top folders):
  Inbox                 100,000 (capped — actual count likely higher)
  [Mailstrom]/Expired    51,545
  Unroll.me              14,028
  Unroll.me/Unsubscribed 12,658
  Sent                    6,589
  Named person folders:   Ger (158), family (20), kirsta (17), dad (2),
                          Killian (1)

Top 20 senders are entirely commercial (Groupon, eBay, Ann Taylor, etc).
Real human correspondents identified by filtering out commercial domains.

Key contacts identified for first ingestion pass:
  Patrick Mangan    pjmangan@gmail.com           235 from, 1,868 total, 2007-2026
  James Root        jcroot@gmail.com             115 from, 2011-2025
  Brian Ferrier     ferrierscout@gmail.com       438 from, 2021-2025
  Angela Page       page.angela@gmail.com        111 from, 2021-2024
  Kate Elkington    kateelk@gmail.com            101 from, 2016-2025
  David Port        dportmd@icloud.com            83 from, 2022-2026
  William Renahan   william.renahan@blackstone.com  39 from, 2022-2025
                    william.renahan@dpimc.com       18 from, 2017-2022
  Chris Zichello    czichello@gmail.com           13 from, 2021-2025
  Nicholas Farnham  nfarnham@gmail.com            35 from, 2011-2026
  Brian Farnham     farnhambn@gmail.com           22 from, 2012-2026
  Timothy Farnham   tfarnham@mtholyoke.edu        21 from, 2021-2023

Notable: William Renahan has two email addresses (Blackstone and DPIMC)
across different employment periods — validates the need for the
contact_identifiers model with multiple identifiers per person.

Notable: Pat's email corpus (1,868 messages, 2007-2026) pre-dates the
iMessage corpus (2018-present) by over a decade. Combined with iMessage
(13,560 group + 963 bilateral), total Pat touchpoints exceed 16,000
across two channels spanning nearly 20 years.

Notable: Significant asymmetry in Pat correspondence — 1,349 outbound
(Sent) vs 235 inbound (Inbox). Likely explained by Pat replying to
Tom's work email addresses (UBS, Citi, Barclays) rather than Yahoo.
Work email corpus is irrecoverable (noted in Known Corpus Gaps).

### ParsedNote field mapping (proposed)

    From/To/CC     → participants (list[str])
    Subject        → title (str)
    Date           → created_at (str, ISO timestamp)
    Body           → body (str, HTML stripped)
    Message-ID     → metadata["message_id"] (deduplication key)
    Thread-ID      → thread_id (str, groups replies via In-Reply-To/References)
    Direction      → metadata["direction"] "sent" | "received"

### Scripts created (2026-03-27)

All in scripts/yahoo/:
  yahoo_header_scanner.py  — Pass 1: IMAP header scan → SQLite index
  yahoo_index_query.py     — Query the header index for contact analysis
  yahoo_imap_probe.py      — Initial IMAP folder/contact probe
  yahoo_imap_debug.py      — Targeted search debugging
  yahoo_imap_export_test.py — Standard vs export server comparison
  yahoo_imap_list_from.py  — List emails from a specific contact
  yahoo_imap_census.py     — Full contact census across all folders

### New infrastructure created (2026-03-28)

**Parser: pke/parsers/yahoo_mail_parser.py**
  Thread-aware parser that converts MBOX files into ParsedNote objects.
  Pipeline: emails → threads (References chain) → bursts (4h gap) → ParsedNote
  Key design: uses the last email per burst as the body, preserving the
  full conversation context in quoted text rather than stripping quotes
  and losing other participants' contributions.
  Tested: 1,868 emails → 1,216 bursts, avg 5,734 chars per burst.

**Ingestor: pke/ingestion/yahoo_mail_ingestor.py**
  Bridges parser output to Supabase. Writes to three tables:
    email_conversations — keyed by participant hash (sorted participant set)
    email_messages — per-email metadata (Message-ID, headers)
    retrieval_units — burst content + embedding (unified retrieval)
  Dry run tested: 1,868 emails → 171 conversations, 1,216 bursts.

**SQL Migration: scripts/add_retrieval_units_and_email_tables.sql**
  Creates: retrieval_units, email_conversations, email_messages,
  contacts, contact_identifiers, match_retrieval_units RPC.
  NOT YET RUN against Supabase — pending identity resolution.

**Thread analysis: scripts/yahoo/yahoo_thread_analysis.py**
  Analyzed Pat's corpus: 900 threads, 90% content redundancy in
  quoted replies. Informed the decision to preserve full conversation
  bodies rather than strip quotes.

**MBOX inspector: scripts/yahoo/yahoo_mbox_inspect.py**
  Corpus structure: 1,840/1,868 have plain text, only 28 HTML-only,
  31 attachments total, all multipart/alternative.

### Key design decisions (2026-03-28)

**Unified retrieval architecture (DECIDED)**
  All content sources write to a single retrieval_units table.
  One embedding column, one search RPC (match_retrieval_units),
  one place to tune retrieval quality. Source-specific tables hold
  structural metadata only. Replaces the pattern of extending
  match_chunks with LEFT JOINs for each new source.

  Migration path:
    1. Create retrieval_units table (SQL migration written)
    2. Email ingestor writes to it first
    3. Backfill existing Joplin chunks and iMessage bursts
    4. Simplify match_chunks RPC to query retrieval_units only
    5. Future sources write to retrieval_units from day one

**Conversation model (DECIDED)**
  A conversation is defined by its exact participant set, not by
  topic or thread. Tom + Pat is one conversation. Tom + Pat + James
  is a different one. Conversations persist across years, across
  topics, across silence gaps.

  Hierarchy:
    Conversation — unique participant set (hashed)
    Thread — topical exchange within a conversation (References chain)
    Burst — time-segmented cluster within a thread (4h gap)
    Contribution — one person's new content at one point in time

  When participants change (someone added/dropped), a new conversation
  is created. Linking across participant set changes is deferred.

**Full conversation body preservation (DECIDED)**
  The parser preserves the full email body including quoted replies,
  rather than stripping quotes. Rationale: the quoted text contains
  other participants' contributions which are often the only record
  of what they said (the sender's replies went to work email addresses
  not in this mailbox). The last email per burst contains the complete
  conversation snapshot.

  Thread analysis confirmed 90% of email content is quoted text.
  Stripping it produced fragments that lost conversational context.
  Preserving it produces richer, more complete retrieval units.

**Identity resolution needed before ingestion (BLOCKING)**
  Dry run revealed William Renahan appears as 5+ different email
  addresses across employers, creating duplicate conversations that
  should be unified. Similarly pj.mangan vs pjmangan splits Pat.
  thomas.farnham appears twice in some participant lists (case/domain
  variation).

  The contacts + contact_identifiers tables must be populated and
  the parser must resolve identifiers before hashing participants.
  Without this, 171 conversations would exist where ~40-50 should.

### Next actions

1. Populate contacts + contact_identifiers in Supabase with known
   identifiers for target contacts (William's 5 addresses, Pat's 2,
   Thomas's variations, Chris's variations)
2. Add identifier resolution step to parser — normalize email
   addresses through contacts table before participant hashing
3. Run SQL migration against Supabase
4. Run real ingestion for Pat's MBOX
5. Generate embeddings for new retrieval_units
6. Update match_chunks RPC or plugin to query retrieval_units
7. Verify email bursts surfacing in Obsidian Reflections panel
8. Update selective downloader to support multi-contact deduplicated
   download
9. Download remaining target contacts
10. Full ingestion pass for all contacts

---
### Parallel Track: 9.15 — Content Curation Agent

Status: FOUNDATION BUILT — 2026-03-29
Location: scripts/content_agent/

Four-agent pipeline (Scout → Editor → Connector → Composer) created.
All code written. Not yet tested against live sources.

Remaining before first run:
  1. Add NEWSAPI_KEY to .env (newsapi.org free tier)
  2. pip install feedparser
  3. Validate RSS feed URLs: python -m scripts.content_agent.scout --dry-run
  4. Confirm import paths work from repo root
  5. Set Obsidian vault path
  6. First live daily run
### Parallel Track: 9.15 — Content Curation Agent

Status: PIPELINE TESTED AND RUNNING — 2026-04-04
Branch: feat/9.15-content-curation-agent
Location: scripts/content_agent/

Four-agent pipeline (Scout → Editor → Connector → Composer) tested
end-to-end. First daily drop delivered to Obsidian vault on 2026-04-04.

First run results (2026-04-04):
  Scout: 133 items (78 RSS, 58 NewsAPI) from 11 working feeds
  Editor: 8 items survived (94% kill rate)
    - Practitioner: 2, Reader: 1, Builder: 5
    - Editor notes: "Strong coverage of agentic AI in production
      finance systems and governance challenges"
  Connector: 8/8 items found personal corpus connections (24 total)
  Composer: daily drop delivered to Obsidian vault

Notable items from first run:
  - "Is the Three Lines Model Still Valid in the Agentic Era?"
    (Corporate Compliance Insights) — directly relevant to ERM work
  - "Banking beyond the law" (Aeon) — historical parallel, Reader pillar
  - "We replaced RAG with a virtual filesystem" (HN) — PKE-relevant

Code fixes applied during testing:
  - Added load_dotenv() to scout.py, editor.py, connector.py
    (.env file not auto-loaded without explicit call)
  - Fixed null summary crash in editor.py line 133:
    item.get("summary", "")[:300] → (item.get("summary") or "")[:300]
  - ArXiv feeds have SSL certificate issues on Windows — pending removal
  - HBR feed has encoding mismatch — pending URL fix or removal
  - Allen AI Blog feed has malformed XML — pending removal

Deployment architecture (designed, not yet implemented):
  Server (GitHub Actions, daily 6 AM):
    Scout → Editor → Composer (without personal connections)
    Output pushed to OneDrive → syncs to Obsidian vault
    Requires: repo set to private, API keys in GitHub Secrets
  Local (on demand from Obsidian):
    "Enrich today's brief" → Connector runs locally, starts PKE API,
    annotates daily drop with personal corpus connections
    "Weekly synthesis" → Composer weekly mode against accumulated drops
  Obsidian Shell Commands plugin for triggering local processes

Remaining before automated deployment:
  1. Make GitHub repo private (contains personal career/strategy docs)
  2. Set up GitHub Actions workflow with cron schedule
  3. Add ANTHROPIC_API_KEY and NEWSAPI_KEY as GitHub Secrets
  4. Configure output push to OneDrive or repo
  5. Install Obsidian Shell Commands plugin
  6. Configure two Obsidian commands: Enrich + Weekly Synthesis
  7. Remove broken feeds from sources.json (ArXiv, Allen AI, HBR)
  8. Populate books.json over time

---


## Also update the Venv/Environment section — add:

### Yahoo Mail IMAP credentials

Stored in .env:
```
# Yahoo Mail — IMAP access for PKE email parser (milestone 9.13)
# App password generated at login.yahoo.com/account/security
# Required: two-step verification enabled on Yahoo account
YAHOO_EMAIL=thomas.farnham@yahoo.com
YAHOO_APP_PASSWORD=[redacted]
```

Export IMAP server: export.imap.mail.yahoo.com (port 993, SSL)
Standard IMAP server: imap.mail.yahoo.com (port 993, SSL) — 10K limit, not used
### Deferred: Yahoo Inbox Cleanup Agent

Noted in original 9.13 design as "Inbox cleanup agent — separate project,
noted for future planning."

Now actionable: the header index (yahoo_index.db, 187,320 messages) provides
the targeting data needed to identify and remove commercial noise at scale.

Approach:
  - Query the header index to identify bulk senders (>50 messages, commercial domains)
  - Generate a delete list with sender, count, and sample subjects for review
  - Dry-run mode: show what would be deleted, require explicit confirmation
  - Execute via standard IMAP server (imap.mail.yahoo.com, not export server)
  - IMAP DELETE flow: flag messages as \Deleted, then EXPUNGE
  - Safety: never delete from senders who appear in the contacts table
    or who have been part of bidirectional correspondence
  - Separate pass: create Yahoo mail filters/rules for high-volume
    commercial senders to prevent backlog from rebuilding

Why standard IMAP server (not export):
  The export server is designed for read-only bulk extraction.
  The standard server sees the most recent 10K messages per folder,
  which is where the active junk accumulates. Deleting from the
  standard server frees up the visible window and may expose older
  messages that were previously hidden by the 10K cap.

Status: DEFERRED — build after parser and ingestion are complete.
Dependency: contacts table in Supabase (safety filter for delete targeting).
---

## Downstream Milestones

### 9.3 — Personality Skin v1
Producer writes the first system_prompt based on corpus analysis output.
Status: DEFERRED pending 9.4 prototype.
Rationale: need the Companion Engine generation loop to run listening
sessions before the skin can be validated. Build 9.4 prototype first.
Key note: group is highly sarcastic — sarcasm register must be named
explicitly in the system prompt. Warmth keywords in corpus analysis
are misfiring (brilliant, legend used ironically).

### 9.4 — Companion Engine (prototype first)
Standalone script: scripts/test_companion.py
- Takes journal excerpt as input
- Retrieves top N bursts from imessage_bursts via PKE API
- Assembles prompt with placeholder system prompt
- Calls Claude API, prints response
Status: NOT STARTED

### 9.5 — Companion Plugin Integration
Wire Companion Engine into Obsidian plugin. Unprompted intervention
model. Separate visual presence.
Status: NOT STARTED

### 9.9 — Obsidian Parser + Migration
Add Obsidian vault as ingestion source. Migrate Joplin corpus.
Status: NOT STARTED

### 9.11 — Handwritten Journal Digitization
Moleskine journals. Pre-digital record.
Status: NOT STARTED

---

## Final Supabase State (as of 9.1 close)

- chunks table: imessage 1,279 rows ✅ / joplin 866 rows ✅
- imessage_threads: 4 rows
- imessage_participants: populated
- imessage_messages: 14,566 rows
- imessage_bursts: 1,279 rows, 1,279 with embedding ✅

---

## Known Corpus Gaps

### Irrecoverable
- Hotmail (pre-~2005) — dormant account, likely purged
- JP Morgan Chase corporate email — corporate IT retention policies

### Potentially Recoverable
- Early Patrick correspondence (email) — Patrick may have archived
- Early James / other friends — same principle
- Gmail forwards — check Google Takeout

### iMessage — not yet exported
- James, Chris, William bilateral threads
- Any sub-group threads (Thomas + Patrick + James etc)

### Journal
- 1,489 notes ingested. Coverage likely uneven by period.
- Pre-digital Moleskine journals not yet digitized (milestone 9.11)

---

## Test Maintenance — Known Rules

### embed_chunks.py — source loop pattern
Every new source loop added requires updating TWO places in
tests/unit/test_embed_chunks.py:
1. make_clients() helper — add fetch method with return_value=[]
2. Every test that builds supabase = MagicMock() directly
Failure: silent infinite loop, test hangs 3+ minutes with no error.

### match_chunks RPC — return type changes
Requires DROP FUNCTION before CREATE OR REPLACE.
Canonical sequence in add_match_functions.sql:
  DROP FUNCTION IF EXISTS match_chunks(vector, integer, text, integer);
  CREATE OR REPLACE FUNCTION match_chunks(...) ...

### match_chunks RPC — new source types
When a new source is added, update match_chunks:
- Add LEFT JOIN to the relevant source table
- Extend COALESCE chain for note_title and notebook

---

## Venv Activation (Windows PowerShell)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "C:\Users\thoma\Documents\dev\Personal-knowledge-engine\venv\Scripts\Activate.ps1"
```

Note: venv is named `venv` not `.venv`.

---

## Previous Milestones

- 8.9.4 — Deterministic Ingestion Baseline ✅ (2026-03-03)
- 8.9.5 — Real Embeddings ✅ (2026-03-06)
- 8.9.6 — Chunking for Long Notes ✅ (2026-03-07)
- 8.9.7 — Retrieval API ✅ (2026-03-08)
- 8.9.8 — Obsidian Insight Plugin ✅ (2026-03-14)
- 9.1 — iMessage Parser ✅ (2026-03-22)
- 9.2 — Corpus Analysis Tool ✅ (2026-03-23)
- Plugin improvements (suppression, Why?, tooltip, debounce) ✅ (2026-03-27)
