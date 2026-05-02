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

Status: DEPLOYED — 2026-04-05
Branch: merged to main
Location: scripts/content_agent/

Four-agent pipeline (Scout → Editor → Connector → Composer) deployed
and running on GitHub Actions. Daily drops committed to repo automatically
at 6:00 AM EST.

Pipeline results (2026-04-05):
  Scout: 133 items (78 RSS, 7 working feeds + NewsAPI 6 queries)
  Editor: 7 items survived (95% kill rate)
  Connector (redesigned 2026-04-05):
    - PKE synthesis: 10 connections kept, 11 dropped as weak
    - Book matching: 6 genuine connections across 5 items
    - Total: 16 meaningful connections (down from 30 false positives)
  Composer: daily drop delivered to Obsidian vault

Connector redesign (2026-04-05):
  Previous: keyword matching for books, no PKE relevance notes
  Current: three-step Claude-powered pipeline:
    Step 1 — Find PKE candidates (semantic similarity, unchanged)
    Step 2 — Synthesize PKE connections via Claude (explain or discard)
    Step 3 — Find book connections via Claude (conceptual, not keyword)
  Result: eliminated false positives like Antigone matching "state"
  in a programming article. Connections now include one-sentence
  explanations of the intellectual relationship.

Book database populated (2026-04-05):
  32 books with thematic tags, keywords, and core ideas.
  Includes: Federalist Papers, Frankenstein, Foucault, Borges,
  Arendt, Orwell, Aristotle, Thucydides, Dostoevsky, and 23 others.
  The Connector queries by conceptual adjacency, not keyword overlap.

GitHub Actions deployment (2026-04-05):
  Workflow: .github/workflows/content-agent-daily.yml
  Schedule: daily at 11:00 UTC (6:00 AM EST)
  Steps: Scout → Editor → Composer → commit to repo
  Secrets: NEWSAPI_KEY and ANTHROPIC_API_KEY stored in GitHub Secrets
  Permissions: contents: write for commit step
  Manual trigger: available via workflow_dispatch
  Note: Connector skipped in automated run — no PKE API on GitHub
  servers. Personal corpus enrichment runs locally on demand.

CI fix (2026-04-05):
  Added types-requests to mypy install step in ci.yml to resolve
  Library stubs not installed errors on GitHub runners.

Remaining:
  Completed (2026-04-05 session 2):
  - Obsidian Shell Commands plugin installed and configured
  - Four commands: Start API, Stop API, Enrich, Weekly Synthesis
  - API auto-starts on Obsidian launch, auto-stops on quit
  - Content Briefs folder sorted newest-first
  - Tagging workflow: #post-seed + [[Daily Drop]] wiki links

Remaining:
  1. Automate PKE Reflections plugin restart after API start
  2. Scout dedup across days (backlog — ~10 line change to Scout)
  3. Continue populating books.json
  4. Run daily for 4 weeks — validation period
  5. Producer review of Scout raw output after 30 days
  6. Future: Microsoft Graph API / OneDrive delivery (Option 2)
  7. Delete unused start_pke_api.bat from repo
---
### Reflections Panel Redesign ✅ (2026-04-09)
Branch: merged to main (pke-obsidian-plugin repo)
Spec: specs/REFLECTIONS_PANEL_REDESIGN_SPEC.md

Progressive disclosure card layout replacing flat passage list.

What shipped:
  - Collapsed view: source icon + note title + date + extractive
    sentence + Claude Haiku one-line summary (async, cached)
  - Expanded view: full passage + section title + similarity score +
    action buttons (open note, thumbs up/down, link at cursor, dismiss)
  - Source-colored left borders: blue (journal), green (iMessage),
    amber (email)
  - Extractive sentence: word overlap scoring picks most relevant
    sentence from passage, not first sentence
  - Claude summaries: generated via Obsidian requestUrl (CORS fix),
    cached per session to prevent duplicate API calls
  - iMessage formatting: speaker labels on separate lines, multi-word
    names kept together, empty attachment-only lines removed
  - Attachment artifacts ([attachment.jpg] etc) stripped from display
  - Dedup: two-pass — by note_id (highest score), then by matched_text
    prefix (first 200 chars) across different notes
  - Date display: "Mon YYYY" for older, "DD Mon" for recent, "undated"
    for missing entry_timestamp
  - 8 unit tests for suppression and dedup logic (suppression.test.ts)

Cost: ~$1.50-3.00/month for Claude Haiku summaries during daily writing

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

## Current Milestone: 9.9 — Obsidian Parser

Status: IN PROGRESS
Branch: feat/9.9-obsidian-parser

### What this milestone builds

A parser that ingests personal Obsidian vault notes into the PKE
knowledge base, making active daily writing visible to the Reflections
panel. Follows the same pluggable parser pattern as Joplin, iMessage,
and Yahoo Mail: source files → parser → ParsedNote contract → ingest
pipeline → retrieval_units.

This is the highest-impact source addition to date. The Joplin corpus
is historical (pre-Obsidian). iMessage and email are relational.
Obsidian is where active thinking happens — journal entries, LinkedIn
drafts, reading notes. Without this parser, the Reflections panel
cannot surface connections to today's writing.

### Source files — what gets ingested

Three files in the Obsidian vault, selected via YAML frontmatter tag:

1. **Running Journal** — the primary writing file. Date-stamped entries
   (M/D/YY format) ranging from one-liners to multi-paragraph essays.
   Contains links, blockquotes, Obsidian wiki links, highlights, tables,
   and embedded references to Daily Drops. Entries span personal
   reflection, career strategy, PKE development notes, fitness tracking,
   book club, family, travel, and intellectual exploration.

2. **LinkedIn Posts** — published and draft LinkedIn posts. Date-stamped,
   self-contained entries. Each post is a complete thought piece, typically
   200-500 words, covering AI governance, Federalist Papers, epistemic
   philosophy, and practitioner experience.

3. **Reading List** — loosely structured reading notes. Currently focused
   on "Ladies and Gentlemen, The Bronx Is Burning" (Mahler). Stream-of-
   consciousness with names, references, personal connections, embedded
   quotes. No consistent date headers.

Vault path: C:\Users\thoma\OneDrive\Apps\New folder\Journal

### Opt-in mechanism — YAML frontmatter tag (DECIDED)

Files are selected for ingestion via YAML frontmatter:

```yaml
---
pke-ingest: true
pke-title: "Journal"
---
```

`pke-ingest: true` — required. Parser skips all files without this flag.
`pke-title` — optional. Human-readable title displayed in the Reflections
panel. Falls back to filename stem if not present.

This approach provides:
- Explicit per-file opt-in control at the point of writing
- Automatic exclusion of system documents (ARCHITECTURE.md mirrors,
  daily drops, specs) without needing a blocklist
- Clean alignment with the System Document Ingestion Boundary
  (ARCHITECTURE.md Section 2)
- Future extensibility — additional frontmatter fields can be added
  without changing the parser contract

### Note ID strategy (DECIDED)

Obsidian files have no intrinsic UUIDs. Note ID is derived from the
vault-relative file path:

```
obsidian::<sha256(vault-relative-path)>
```

Example: `obsidian::a1b2c3d4...` for `Journal/my-journal.md`

Properties:
- Deterministic — same file always produces same ID
- Stable across re-ingestion runs
- File rename → new ID (correct behavior: old version cleaned up,
  new version ingested fresh)
- Collision-free across sources (prefixed with `obsidian::`)

### Date header formats observed in source files

The running journal and LinkedIn file use M/D/YY as the primary
format, with variants the parser must tolerate:

```
5/1/26 -          ← standard, trailing dash
4/24/26 -         ← standard
4/21//26 -        ← double slash typo
03/28/26 -        ← zero-padded month
4/12/2026         ← four-digit year
4/7/36            ← typo (should be 4/7/26) — parser should handle gracefully
4/3/2026          ← four-digit year, LinkedIn file
3/26/26           ← LinkedIn file
##### 3/28/26     ← Markdown heading prefix
```

The existing date_parser.py from the Joplin chunker handles this
range of formats. Confirmation test required with actual source
date headers.

The Reading List file has no date-stamped entries — only a loose
"March 2026" header. This file is treated as a reference document,
not a date-segmented journal.

### Obsidian-specific syntax handling (DECIDED)

Strip Obsidian syntax markers while preserving text content. These
markers add noise to embeddings and create false semantic connections
(e.g., wiki links to Daily Drops would match on the drop content
rather than the journal entry's own meaning).

Syntax to strip:
- Wiki links: `[[Daily Drop 2026-04-07#heading]]` → "Daily Drop 2026-04-07 heading"
- Highlights: `==text==` → "text"
- Callouts: `> [!attention]` → strip callout marker, preserve text
- Obsidian comments: `%%text%%` → strip entirely

Syntax to preserve as-is:
- Standard Markdown (headers, bold, italic, links, blockquotes, lists)
- Code blocks
- Tables
- URLs and external links

### Chunking strategy (DECIDED)

Reuse the existing chunking module (pke/chunking/chunker.py).
The chunker operates on the ParsedNote contract, not on source-
specific formats. Archetype detection runs on content shape.

Per-file chunking behavior:

**Running Journal** → Archetype A/B detection. Split on date headers
(M/D/YY pattern). Each dated entry becomes a retrieval unit. Long
entries (500+ words) may be further split on paragraph boundaries.
Short consecutive entries merged if below ~100 token threshold.

**LinkedIn Posts** → Archetype A detection. Split on date headers.
Each post becomes its own retrieval unit. Posts are self-contained
and substantial enough (200-500 words) to stand alone.

**Reading List** → No date headers to split on. If below chunking
threshold (~1000 chars), ingest as single retrieval unit. If above,
split on paragraph/section boundaries. Closest to Archetype C
(reference document without dated log).

### ParsedNote field mapping

```
filename / pke-title  → title
file body              → body (after syntax stripping)
file mtime or dates    → created_at / updated_at
YAML frontmatter       → metadata
vault-relative path    → source_file
source_type            → "obsidian"
privacy_tier           → 2 (personal/journal)
participants           → None
dominant_sender        → None
thread_id              → None
thread_type            → None
person_ids             → None (reserved for entity layer)
```

### Where it writes — retrieval_units (DECIDED)

Obsidian content writes to the retrieval_units table, following the
unified retrieval architecture established in milestone 9.13.

Each retrieval unit row contains:
- content: chunk text (syntax-stripped)
- source_type: "obsidian"
- source_id: note ID (obsidian::<hash>)
- note_title: from pke-title frontmatter or filename
- entry_timestamp: from date header (if detected) or file mtime
- embedding: generated by embed_chunks.py backfill
- privacy_tier: 2

The Reflections panel already renders journal sources with blue
left borders. Obsidian content will surface with this same styling.

### Ingestion trigger — batch CLI (DECIDED)

Manual batch run via CLI command. Same pattern as all other parsers.

```
pke ingest-obsidian --vault-path "C:\Users\thoma\OneDrive\Apps\New folder\Journal" --dry-run
pke ingest-obsidian --vault-path "C:\Users\thoma\OneDrive\Apps\New folder\Journal"
```

Run manually after a writing session, or via Shell Commands plugin
button in Obsidian. No file watcher, no on-save ingestion for v1.

Delete-and-rewrite per file on each run. For 3 files this is fast
and eliminates drift between source and database.

Future: file watcher (Option B) as a fast-follow. The parser
function is the same — the watcher just calls it on file change
events instead of on a full scan. ~20 lines using Python watchdog
library.

### Module structure

```
pke/parsers/obsidian_parser.py        — vault scanner + Markdown parser → ParsedNote
pke/ingestion/obsidian_ingestor.py    — bridges ParsedNote → retrieval_units
pke/cli/ingest_obsidian.py            — Typer CLI: pke ingest-obsidian
tests/unit/test_obsidian_parser.py    — parser unit tests
tests/unit/test_obsidian_ingestor.py  — ingestor unit tests
```

### Next actions

1. Add `pke-ingest: true` and `pke-title` frontmatter to all three
   Obsidian source files
2. Create feat/9.9-obsidian-parser branch
3. Build obsidian_parser.py — frontmatter reader, syntax stripper,
   vault scanner, ParsedNote emitter
4. Write parser unit tests with samples from actual source files
5. Confirm date_parser.py handles M/D/YY with trailing dash format
6. Build obsidian_ingestor.py — ParsedNote → retrieval_units writer
7. Write ingestor unit tests
8. Build CLI command (ingest_obsidian.py) with --vault-path and --dry-run
9. Dry run against live vault
10. Real ingestion run
11. Run embed_chunks.py backfill for new retrieval_units
12. Verify Obsidian entries surfacing in Reflections panel
13. PR and merge

### Deferred from this milestone

- **Joplin corpus migration to retrieval_units** — backfilling existing
  Joplin chunks and iMessage bursts into retrieval_units is infrastructure
  cleanup, not part of the Obsidian parser. Tracked separately.
- **File watcher (on-save ingestion)** — batch CLI is sufficient for v1.
  File watcher is a fast-follow once the pipeline is validated.
- **Incremental ingestion (content hash skip)** — not needed for 3 files.
  Worth building when tagged files reach 10+. Store content SHA256 in
  metadata, skip files whose hash hasn't changed since last run.
- **Additional frontmatter fields** (pke-type, pke-notebook) — not needed
  for v1. Archetype detection handles chunking decisions. Add if retrieval
  quality analysis reveals a need.

---


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

## Backlog

### Plugin repo backlog (pke-obsidian-plugin)

1. **CI workflow for plugin repo** — add .github/workflows/ci.yml
   with npm build and npm test on push. Same hygiene standard as
   pipeline repo. Currently no automated checks on push.

2. **DOM element-by-element rendering for iMessage** — replace
   innerHTML approach with DOM construction for speaker label
   bolding. Security hardening for community plugin distribution.
   Current approach is safe for personal corpus but not for
   untrusted content.

3. **Automated PKE plugin restart on Obsidian start** — plugin
   needs manual restart after API auto-starts. Investigate
   Obsidian API for programmatic plugin reload.

4. **Add created_at fallback for dates** — retrieval API should
   return note-level created_at as fallback when entry_timestamp
   is null. Requires Python change in PKE pipeline repo
   (retriever.py query response) and TypeScript change in plugin
   (date rendering logic). Currently shows "undated" for notes
   without entry_timestamp.

5. **Joplin deep links** — "Open note" button should construct
   joplin://x-callback-url/openNote?id={note_id} for Joplin
   sources. Future Obsidian sources use obsidian:// protocol.
   iMessage/email sources: button hidden or disabled.

6. **Code review process** — establish periodic review sessions
   for plugin and pipeline codebases. Spec checklist should
   include runtime environment considerations (e.g. CORS in
   Electron) to prevent integration bugs.

7. **UI testing with Playwright + Electron** — prototype automated
   UI testing for the Obsidian plugin. Learn and evaluate, not
   build immediately. Transferable enterprise skill.

### Pipeline repo backlog (Personal-knowledge-engine)

8. **Scout dedup across days** — load previous day's scout output
   JSON, add URL hashes to seen set before dedup. Prevents same
   article appearing in consecutive daily drops. ~10 line change.

9. **Data layer cleanup** — investigate duplicate journal content
   across different note_ids in Supabase. Same passage text
   appearing under different note_ids causes panel duplicates
   even with note_id dedup.

10. **Delete unused start_pke_api.bat** — replaced by Obsidian
    Shell Commands inline command.

### Design items (not yet implementation-ready)

11. **Journal influence on Editor** — weekly script extracts 3-5
    thematic phrases from recent journal entries via PKE API +
    Claude. Editor prompt reads these as context signal. Calibrates
    editorial judgment toward live themes without creating a filter
    bubble. Scout stays blind to corpus.

12. **Scout Directives (vault-as-control-surface)** — a single
    Obsidian note (Scout Directives.md) that the Scout reads on
    each run. Three sections: Research Topics (temporary NewsAPI
    queries), Add Sources (new RSS feeds), Remove Sources. No code
    changes needed to adjust the Scout's behavior. Architectural
    principle: vault-as-control-surface.

13. **Books architecture transition** — replace books.json with
    a Book Club Library.md note in Obsidian vault. Obsidian parser
    (9.9) ingests it into PKE corpus. Connector queries PKE API
    for book connections instead of reading static JSON. Books
    become part of the corpus, not a separate system. Depends on
    9.9 Obsidian parser.

14. **Microsoft Graph API / OneDrive delivery** — push daily drops
    directly to user's OneDrive folder via Graph API. OAuth app
    registration, refresh token management, file upload logic.
    Eliminates git pull requirement. Enterprise integration pattern.
    The delivery step is isolated in the Composer — single-layer
    swap from git commit to API push.

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
