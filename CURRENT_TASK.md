# CURRENT_TASK.md
## Milestone 9.1 — iMessage Parser
Last updated: 2026-03-22

## Status: NEARLY COMPLETE

Branch: feat/9.1-imessage-parser

### Completed This Session
- ✅ Parser (imessage_parser.py) — 50 tests passing
- ✅ Ingestor (imessage_ingestor.py) — 27 tests passing
- ✅ CLI (ingest_imessage.py) — Typer, registered as pke ingest-imessage
- ✅ Schema migration (add_imessage_tables.sql) — run against Supabase
- ✅ SupabaseClient extended (upsert_rows, delete_where, fetch_unembedded_bursts, update_burst_embedding)
- ✅ CLAUDE.md created at repo root
- ✅ All four CSV threads ingested into Supabase:
    Group chat:              13,560 messages, 964 bursts
    Patrick bilateral:          963 messages, 276 bursts
    Patrick + James + William:   42 messages,  38 bursts
    Patrick + William + Glenn:    1 message,    1 burst
    Total:                   14,566 messages, 1,279 bursts
- ✅ embed_chunks.py extended to backfill iMessage burst embeddings

### Remaining — Do First Next Session
1. Fix hanging test: tests/unit/test_embed_chunks.py::TestEmbedChunksCore::test_exits_cleanly_when_no_chunks
   - Root cause: mock not properly stopping the while True loop
   - Our burst loop follows same pattern — same fix needed for both
   - Do NOT use --no-verify after this is fixed

2. Run embedding backfill:
   python -m pke.cli.embed_chunks
   This will embed all 1,279 bursts (currently embedding IS NULL)
   Cost: ~1,279 OpenAI API calls

3. Verify in Supabase:
   SELECT source_type, COUNT(*) as count, COUNT(embedding) as with_embedding
   FROM chunks GROUP BY source_type;
   Expected: imessage 964 with_embedding = 964

4. Verify in Obsidian:
   Start the PKE API (uvicorn pke.api.main:app --reload)
   Write a journal entry referencing themes from the group chat
   Confirm iMessage bursts surface in Reflections panel

5. Create PR and close milestone 9.1

### Current Supabase State
chunks table:
    imessage: 964 rows, 0 with embedding (needs backfill)
    joplin:   866 rows, 866 with embedding ✅

imessage_threads: 4 rows
imessage_participants: populated
imessage_messages: 14,566 rows
imessage_bursts: 1,279 rows, 0 with embedding (needs backfill)



---

## Parallel Task — Local Platform Setup
**Priority: HIGH — do this before or alongside the iMessage parser**

The goal is a fully sovereign, internet-independent PKE stack.
Everything runs locally. No external dependencies required.
This is both a privacy architecture and an emergency resilience plan.

### Step 1 — Ensure Joplin notes are locally available

OneDrive may be configured for Files On-Demand — files stored
in the cloud and only downloaded when opened. This must be
changed so all files are always available offline.

In File Explorer:
    Right-click the OneDrive icon in the system tray
    → Settings → Account → Choose folders
    Ensure the Joplin sync folder is set to always keep on device

Or right-click the Joplin sync folder in File Explorer:
    → Always keep on this device

Verify: files should show a green checkmark, not a cloud icon.

Confirm the Joplin sync folder path:
```powershell
Get-ChildItem -Path "C:\Users\thoma\OneDrive" -Recurse -Filter "*.md" -ErrorAction SilentlyContinue | Select-Object -First 5 FullName
```

### Step 2 — Download and install Ollama

Ollama manages local model downloads and runs them as a local
API server — the same interface pattern as OpenAI and Anthropic.

    1. Download from: https://ollama.com
    2. Install — accept all defaults
    3. Verify: ollama --version

### Step 3 — Download Llama 3

```powershell
ollama pull llama3
```

This is a one-time download of approximately 4-8GB.
After this it runs fully offline forever.

Hardware note: check which variant is appropriate.
    llama3          — 8B parameters, runs on most modern laptops
    llama3:70b      — more capable, needs a GPU or powerful machine

Check available RAM first:
```powershell
Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum
```

8B model needs ~8GB RAM minimum.
70B model needs ~40GB RAM — likely needs GPU.
Start with llama3 (8B) — can upgrade later.

### Step 4 — Verify Ollama is working

```powershell
ollama serve
```

In a second terminal:
```powershell
ollama run llama3
```

Type a test message. If it responds, the local model is working.
Exit with /bye

### Step 5 — Migrate Supabase to sqlite-vec (deferred milestone)

This is the final step to full local sovereignty.
Supabase is the last external dependency — it holds the
embeddings and indexed content. sqlite-vec replaces it.

Deferred — see ROADMAP.md Cross-Cutting Concerns.
But name it here as the completion step for the resilience plan.

### Why This Matters

In an offline or grid-down scenario the fully configured
local stack provides:
    - Full access to personal note corpus (Joplin sync folder)
    - Semantic retrieval across the corpus (local sqlite-vec)
    - Llama 3 reasoning and generation (Ollama)
    - Obsidian writing environment (local app)
    - PKE retrieval API (local FastAPI + uvicorn)
    - Companion voice (Llama 3 as provider)
    - General world knowledge (Llama 3 training data)

Nothing requires internet. Nothing requires a subscription.
Nothing requires any company to still be operating.

---

## Known Corpus Gaps

A record of what is missing from the PKE corpus and why.
The Observer Layer and Writer Portrait must be calibrated with
awareness that the corpus is incomplete. Absence of evidence
is not evidence of absence.

### Irrecoverable

**Hotmail (pre-~2005)**
Early personal email. Dormant account, likely purged.
Contains correspondence from college and early post-college years.
Period: approximately late 1990s — early 2000s.

**JP Morgan Chase corporate email**
Professional correspondence from JPM years.
Corporate IT retention policies almost certainly purged.
Irrecoverable.

**Other old addresses**
Any additional personal email addresses from early internet era
that are no longer accessible.

### Potentially Recoverable

**Early Patrick correspondence (email)**
Patrick may have Thomas's early emails on his end if he has
maintained the same address. Worth asking.

**Early James / other friends correspondence**
Same principle. Key correspondents from the pre-iMessage era
may have archived emails that Thomas sent them.

**Gmail forwards**
Anything forwarded from old addresses to Gmail would be in
Google Takeout. Worth checking.

### Known Gaps by Channel

**iMessage — group chat**
Near silence 2019-2021. Confirmed bridged by bilateral threads.
Patrick bilateral thread active throughout this period.

**iMessage — bilateral threads**
Patrick thread starts December 2013. Pre-2013 record missing.
James, Chris, William bilateral threads not yet exported.
Any sub-group threads (Thomas + Patrick + James etc) not yet
exported.

**Journal (Joplin)**
1,489 notes ingested. Coverage likely uneven — some periods
heavily journaled, others sparse. Corpus analysis will reveal
temporal distribution.

**Pre-digital record**
Handwritten Moleskine journals — not yet digitized (milestone 9.11).
These may cover the pre-digital gap more than any other source.

### iMessage Export History Archive

The source files are the archive. The database is the index.
This is the same principle as the Joplin corpus — the database
is always reconstructable from source files.

**Immediate practice — date-stamped exports:**
Keep every iMazing export permanently. Never overwrite.
Name convention:
    Messages - Patrick Mangan - 2026-03-15.csv
    Messages - Patrick Mangan - 2027-01-10.csv

This solves the most common case at zero overhead cost.
Disk space is negligible — CSV files are tiny.

**Scenarios this protects against:**
- Edited messages (iMessage allows editing — re-export
  reflects edited version, original is gone from CSV)
- Deleted messages (re-export, re-ingest, message gone)
- iMazing export differences across versions
- Any case where you need the record as it existed
  at a specific point in time

**Future milestone — message history table:**
A proper history archive tracking changes at message level:

```sql
imessage_message_history (
    id           -- same as imessage_messages.id
    version      -- incrementing integer
    text         -- content at this version
    captured_at  -- when this version was first seen
    change_type  -- "created" | "edited" | "deleted"
)
```

Every re-ingest detects differences from existing records
before overwriting. Current state in imessage_messages.
Full history in imessage_message_history.

Deferred — revisit after living with the corpus for a year.
Real overhead: ingestion needs a comparison pass before
upserting. Build it when you have evidence it's needed.

---

The most important conversations in most lives happen out loud.
The PKE corpus captures what was written down. It is working
with the written shadow of a life, not the life itself.

This is a structural limitation that applies across all channels
and must be named explicitly in the Writer Portrait and Observer
Layer calibration.

The Patrick bilateral thread is the clearest example:
    - Weekly phone calls for years left no text record
    - The iMessage thread is logistics around conversations
      that happened verbally and are now gone
    - "Give me a call in 10 min" is evidence of a call
      the corpus will never contain
    - The pre-Killian period — the richest phase of the
      friendship — was primarily conducted by phone and
      in person, not by text

The corpus interpretation rule:
    Thin text record ≠ thin relationship
    Frequent logistics messages = evidence of oral relationship
    The written record understates relationships that were
    primarily conducted by phone or in person

The Observer Layer should be calibrated to understand:
    - What is present in the corpus
    - What is structurally absent (oral record)
    - What the written residue implies about the unwritten whole
    - "The corpus is sparse here" is different from
      "the relationship was sparse here"

Writer Portrait note (to be added when built):
    "Patrick as captured in the corpus is the text version
    of a friendship that was primarily conducted by phone
    and in person for many years. The corpus understates
    both the volume and depth of the relationship,
    particularly pre-2015 and pre-Killian."

---

These items are deferred to the Obsidian plugin testing milestone.
Each will be implemented alongside its test cases.

1. **Auto-retry / status indicator** — when the API is not reachable
   on plugin load, poll every 30 seconds rather than showing a static
   error. When the API comes online the panel wakes up automatically
   without requiring a plugin toggle. Show a subtle "connecting..."
   indicator while waiting. Implement alongside plugin test cases.

2. **Hover context expansion** — on hover over a reflection passage,
   show 10 lines above and 10 lines below the matched text from the
   source note. Bounded context window — not the full note.
   Requires new API endpoint: GET /note/{note_id}/context
   passing char_start + line_count. Returns only the surrounding
   window. Also lays the groundwork for deep link paragraph
   navigation (milestone 9.9 dependency).

3. **Relevance explanation** — two layers:
   a) Keyword highlighting — highlight words in the passage that
      overlap with the current writing. Visual, immediate, no
      generation required. Computable client-side.
   b) Subtle confidence indicator — similarity score expressed
      visually (bar, dot intensity, colour) not as a raw number.
      "Strong match" vs "weaker connection" without technical noise.
   Generated one-line explanations ("surfaced because: both discuss
   anxiety about career decisions") deferred to Observer Layer
   milestone — that's the right home for AI commentary on
   what's being surfaced and why.

4. **Query scope control** — selection mode: user highlights text
   to trigger a targeted reflection query from exactly that selection.
   Turns the panel from ambient to intentional.

5. **HTML stripping** — Joplin export artefacts visible in some
   matched_text passages. Strip at parse time in the chunker.

6. **Navigation/deep links** — non-functional until Joplin → Obsidian
   migration complete (milestone 9.9).

7. **Relevance ranking** — personal relevance scoring deferred to 8.9.9.
   Continue capturing specific cases that feel off.

---

Four phases to a working end-to-end prototype:

    Phase 1 — Get the data in (next milestone)
        iMessage parser. Conversation burst ingestion.
        Group chat corpus in the PKE pipeline.

    Phase 2 — Run the analysis
        Corpus Analysis Tool against ingested corpus.
        All eight dimensions. Statistical + interpreted report.
        Producer reads and writes first personality descriptor.

    Phase 3 — First generation
        Simple script — not the full plugin yet.
        Pass a journal excerpt, get a response in the group voice.
        Does it sound right? Adjust. Listen again.

    Phase 4 — Plugin integration
        Wire into Obsidian. Unprompted model.
        Engagement thread. Separate visual presence.

The first version will be off in ways you can feel before you can
articulate. That is the point. The refinement loop is the product.

---

## Data Model Design Notes

### Thread vs Burst — Both Required

A thread is the container. A burst is the retrievable unit.

```
Thread (the whole conversation)
    └── Burst 1 (Jan 28 2018, 4 messages)
    └── Burst 2 (Jan 29 2018, 7 messages)
    └── Burst N (Mar 14 2026, 3 messages)
```

Every burst carries a thread_id linking back to imessage_threads.
This enables:
    - Filtering reflections by thread type (group vs bilateral)
    - Navigating to the source thread for full context
    - Keeping group chat and bilateral corpora separated for
      the Group Voice Synthesis milestone
    - The retrieval API thread_filter parameter (same pattern
      as existing notebook filter)

The bilateral register is distinct from the group register.
Patrick one-on-one with Thomas is a different voice than
Patrick performing for the group. Thread separation
preserves this distinction at the data level.

### Schema — Four New Tables

```sql
imessage_threads (
    id, thread_name, thread_type,   -- "group" | "bilateral"
    participants, source_file,
    date_start, date_end, message_count
)

imessage_participants (
    id, display_name, phone_numbers,
    is_self, thread_ids
    -- v1: phone + display name composite key
    -- known limitation: numbers and names can change over time
    -- full Person/PersonIdentifier model deferred
)

imessage_messages (
    id, thread_id, participant_id,
    timestamp, text, message_type,
    reactions, reply_to_id
)

imessage_bursts (
    id, thread_id,                  -- ← thread attribute here
    date_start, date_end,
    participants, message_ids,
    text_combined, dominant_sender,
    topic_hints, embedding
)
```

### ParsedNote Contract Additions
    source_type      — "imessage"
    participants     — list of display names in burst
    dominant_sender  — who contributed most in burst
    thread_id        — links to source thread
    thread_type      — "group" | "bilateral"
    privacy_tier     — 2 (journal/personal) | 3 (bilateral/relational)
                       group threads = tier 2, bilateral threads = tier 3
                       default retrieval excludes tier 3 unless opted in
    person_ids       — reserved, optional, not populated in v1
                       will link to entity layer when built
                       every parser going forward should reserve
                       this field even if it cannot populate it yet

### Identity Resolution (v1)
Primary key: phone number + display name composite.
Known limitations: numbers and names can change over time.
Full resolution model deferred — revisit when a second
export surfaces ambiguous identities.

---

Manual prototype analysis run against the group chat CSV.
13,579 messages, January 2018 to March 2026.
Five participants: Patrick Mangan, James Root, Thomas,
Chris Zicchelo, William Renahan.

Key findings captured in ROADMAP.md under Personality Skin v1.
These findings are the starting material for the personality descriptor.

Notable gap: near silence 2019-2021. Conversation likely moved
to bilateral threads or a different group thread during this period.
Additional threads should be exported from iMazing to fill the gap.

---

---

## First Steps (next session)

1. Install iTunes / Apple Devices on Windows if not present
2. Connect iPhone and create a local encrypted backup
3. Locate chat.db in the backup:
   C:\Users\thoma\AppData\Roaming\Apple Computer\
       MobileSync\Backup\
4. Extract chat.db and explore the schema
5. Identify target threads (group chat + any individual threads)
6. Design the parser — conversation burst strategy
7. Cut branch and begin implementation

---

## Design Decisions (session 2026-03-14)

### Unit of ingestion — conversation burst
Messages grouped into natural conversation bursts. New burst
begins when gap between messages exceeds configurable threshold
(default: 4 hours). Preserves conversational context and produces
semantically meaningful chunks.

### Attribution
Every message stored with sender attribution. Full burst stored
as matched_text. Per-sender attribution in metadata for Group
Voice Synthesis milestone.

### ParsedNote contract additions needed
    source_type: "imessage"
    participants: list[str]
    sender: str

### Unified timeline
entry_timestamp normalised to ISO format. Recency preference
applies to iMessages on same curve as all other content types.

---

## Downstream Milestones Planned

### Group Voice Synthesis
Build composite AI voice from group chat corpus. Music studio
model — each participant is a channel, Thomas is the producer
controlling channel weights, era filters, mood. Validation by
group recognition. See ROADMAP.md for full design.

### Group Voice Obsidian Integration
Surface group voice as second observer in Obsidian alongside
Reflections panel. Three observers model:
    Reflections    — personal corpus, semantic retrieval
    Group Voice    — composite group voice, generative
    Temporal Mirror — emotional pattern layer (8.9.9)

---

## Previous Milestone: 8.9.8 — COMPLETE ✅

Completed 2026-03-14. Obsidian Insight Plugin running end to end.
Reflections surfacing in real time. See git history for full details.

---

## Status: IN PROGRESS

Branch: feat/8.9.8-obsidian-plugin (PKE repo)
Plugin repo: https://github.com/thomasfarnham-source/pke-obsidian-plugin
VS Code workspace: C:\Users\thoma\Documents\dev\PKE.code-workspace

---

## Progress Log

### Session 2026-03-11
- ✅ Fixed test_retrieval_api.py patch target (routes.query → main)
- ✅ All 385 tests passing
- ✅ Deferred 8.9.7 tests committed on feat/8.9.8 branch
- ✅ Plugin repo created on GitHub (thomasfarnham-source/pke-obsidian-plugin)
- ✅ Plugin repo cloned to C:\Users\thoma\Documents\dev\pke-obsidian-plugin
- ✅ VS Code workspace file created (PKE.code-workspace)
- ✅ Full plugin scaffold designed and generated (see files below)
- ⏳ Scaffold files not yet copied into plugin repo
- ⏳ npm install not yet run
- ⏳ Plugin not yet built or loaded in Obsidian

### Plugin Scaffold Files Generated
All files are in Claude outputs. Need to be copied into the plugin repo:

    pke-obsidian-plugin\
        src\
            main.ts         — entry point, wires everything together
            types.ts        — shared types, settings schema, defaults
            api.ts          — HTTP client for PKE retrieval API
            query-engine.ts — debounce, pause gate, context extraction
            insight-view.ts — sidebar panel and all rendering
            settings.ts     — settings tab UI
        manifest.json       — Obsidian plugin identity
        package.json        — Node project and build scripts
        tsconfig.json       — TypeScript compiler config
        esbuild.config.mjs  — build script
        styles.css          — panel styles
        .gitignore

---

---

## Framing — What This Milestone Is Really Building

The Obsidian insight plugin is the first moment the system becomes
an experience rather than a pipeline. It is the primary consumer-facing
expression of the PKE and the real validation gate for everything built
in 8.9.4 through 8.9.7.

Two retrieval modes define the experience:

**Topical Retrieval** — surfaces passages semantically related to what
the user is writing about now. The default mode. Answers the question:
"what have I thought about this before?"

**Temporal Reflection** — surfaces passages emotionally and situationally
resonant with the current moment, across time. Answers the question:
"what was I feeling the last time I was in a moment like this one?"

Temporal Reflection is the north star. The insight that a recurring
fear never materialized. The recognition that catastrophizing closed
off opportunities that looked obvious in hindsight. The experience of
a younger self telling you "it's going to be ok." No productivity tool
has ever deliberately designed for this. This one does.

The panel is ambient, not intrusive. It surfaces material. The user
does the thinking. The writing process belongs to the user — the system
serves it, never replaces it.

---

## Design Decisions (session 2026-03-09)

### Naming
Surfaced results are called **Reflections** throughout the UI.
Not "results", not "matches", not "memories". Reflections.
Warmer than results, more accurate than memories, less clinical
than matches. Consistent with the temporal mirror framing.

### Query Scope
Send current paragraph plus 2-3 preceding paragraphs of context,
capped at ~500 tokens. Rationale:
- Single paragraph is semantically thin early in an entry
- Full note dilutes the query vector and is slow on large notes
- 2-3 paragraphs gives the retriever enough signal without noise
This is the default. User-configurable in settings.

### Debounce Strategy
Default: ~1000ms after last keystroke.
Pause gate: only fire if current paragraph has changed meaningfully
since last query (character-count delta check). Prevents redundant
API calls while reading or making minor edits.
User-configurable in settings UI (see below).

### Cold Start — Last Session Context
On plugin load, before the user has typed anything, fire one initial
query using the last active note title or last query context, persisted
locally across sessions. Panel wakes up already oriented to where the
user left off. Solves cold start silence and creates continuity
of experience across sessions.

### Settings UI
Exposed in human terms, not technical parameters.

"How quickly would you like reflections to surface?"
    → Immediately (as you pause)
    → After a moment (recommended)
    → Only when I stop writing

"How many reflections would you like to see?"
    → 3 / 5 / 7

"Which notebooks should reflections draw from?"
    → All notebooks
    → Only this notebook
    → [multi-select list]

"Do you prefer older reflections, more recent ones, or both?"
    → Favour older memories
    → Favour recent entries
    → No preference (recommended)

"Do you want to exclude any notes from reflections?"
    → Tag-based exclusion: notes tagged #private, #sensitive,
      or any user-defined exclusion tag will never surface
      as reflections regardless of semantic similarity
    → This is a privacy control within your own corpus —
      useful for notes you've marked sensitive that you don't
      want surfacing unexpectedly while writing other content

Implementation note: exclusion tags are checked at render time
in the plugin — the API returns results as normal and the plugin
filters them out client-side before rendering. This keeps the
API contract simple and the exclusion logic close to the UI.
Alternative: pass exclusion tags to the API as a filter parameter
so excluded notes are never retrieved. Deferred decision — either
approach works, client-side is simpler for 8.9.8.

Tag convention TBD — options:
    #pke-exclude    (explicit, namespaced)
    #private        (natural, already in common use)
    #no-reflect     (descriptive of the specific behaviour)
Recommend letting the user configure their preferred exclusion
tag in settings rather than hardcoding one. "Favour older"
boosts entries with earlier entry_timestamp values; "Favour recent"
boosts more recent ones. "No preference" applies no decay — raw
cosine similarity only (current default behaviour).

Important UX framing: the preference tilts the scoring curve, it
does not create hard cutoffs. A highly relevant recent entry will
still surface even when "Favour older" is selected — the preference
shifts the balance, it does not exclude. This must be reflected in
the UI copy to set correct expectations.

When multi-source content is available (iMessage, email, photos),
the recency preference applies uniformly across all content types.
A message from 2019 and a journal entry from 2019 are treated
identically by the recency curve — source type has no bearing.
This is the unified timeline principle.

### Panel Design
- Lives in the right sidebar
- Updates quietly — never steals focus
- Each reflection shows: date, note title, relevant passage (raw text)
- No relevance scores exposed to the user
- No AI-generated summaries — raw content only, always
- The panel is never a dead end (see Navigation below)

### Navigation — Every Reflection Is a Door
- Click note title → opens source note in Obsidian
- Click passage → opens source note at exact paragraph (char_start)
- Audio chunks → inline play button for original recording
- Image chunks → opens note at photo location

### The Link Feature (not append)
One-click insertion of a dated link to the source note at cursor
position. Format:

    → [Note Title — Date](obsidian://open?note_id=...)

Rationale: the value of the journaling experience is the act of
the user translating thought into language. Appending past text
short-circuits that process. A link acknowledges the connection
exists and invites the user to read the source — but requires
the user to articulate what that connection means to them today.
Over time this creates a genuine link graph in Obsidian through
the act of writing, not automated extraction.

### Relevance Feedback (UI hooks now, backend deferred)
Two lightweight interactions per reflection, designed not to
interrupt writing flow:

- Thumbs up / thumbs down — logged locally for now, no backend
  required in 8.9.8. Data accumulates for future personal
  relevance scoring layer (8.9.9 or later).
- Dismiss — removes reflection from panel for current session.
  Immediately useful UX, generates signal for future scoring.

Rationale for deferring backend: need to live with raw retrieval
first to understand what "low quality" looks like in practice
before building a correction mechanism for it.

---

## Acceptance Criteria

### Deferred Tests from 8.9.7 (completed 2026-03-11)
- [x] tests/unit/test_retriever.py — 25 tests passing
- [x] tests/integration/test_retrieval_api.py — 22 tests passing
- [x] tests/unit/test_embed_chunks.py — 16 tests passing
- [x] All committed on feat/8.9.8 branch

### Core
- [ ] Plugin watches active note for changes
- [ ] Debounce fires after configurable interval (default ~1000ms)
- [ ] Pause gate: only queries if paragraph changed meaningfully
- [ ] Query scope: current paragraph + 2-3 preceding, capped ~500 tokens
- [ ] Cold start: fires initial query from last session context
- [ ] Sends query to POST /query on PKE retrieval API
- [ ] Renders top 3-5 reflections in right sidebar panel
- [ ] Each reflection: date, note title, relevant passage (raw text)
- [ ] No AI-generated summaries — raw content only

### Navigation
- [ ] Click note title → opens source note in Obsidian
- [ ] Click passage → opens source note at exact paragraph (char_start)
- [ ] Audio chunks → inline play button for original recording
- [ ] Image chunks → opens note at photo location

### Link Feature
- [ ] One-click link insertion at cursor position
- [ ] Format: → [Note Title — Date](obsidian://open?note_id=...)
- [ ] Does not append passage text — link only

### Relevance Feedback
- [ ] Thumbs up / thumbs down per reflection
- [ ] Dismiss button per reflection (removes for session)
- [ ] Interactions logged locally
- [ ] No backend scoring in this milestone

### Settings UI
- [ ] Refresh speed (Immediately / After a moment / Only when I stop)
- [ ] Result count (3 / 5 / 7)
- [ ] Notebook filter (All / current / multi-select)
- [ ] Recency preference (Favour older / Favour recent / No preference)
- [ ] Recency preference passed to POST /query as retrieval parameter
- [ ] Note exclusion tag — user-configurable tag name (default: #private)
- [ ] Notes carrying the exclusion tag filtered from rendered reflections

### Edge Cases
- [ ] API server not running → clear message, not silent failure
- [ ] Empty results → quiet state, not error
- [ ] Cold start (no last session) → quiet state
- [ ] Long note → query scope cap enforced, no timeout

### Writing Surface Setup (same milestone)
- [ ] Obsidian vault configured as primary writing tool
- [ ] Light templates by note type installed
- [ ] Journal, medical/reference, book/idea templates defined
- [ ] Migration plan for Joplin notes into Obsidian vault documented

---

## Deferred from 8.9.7 (carry forward — do first)

- [ ] tests/unit/test_retriever.py — retrieval logic with mocked Supabase
- [ ] tests/integration/test_retrieval_api.py — endpoint tests with FastAPI TestClient
- [ ] tests/unit/test_embed_chunks.py — backfill CLI unit tests

---

## Contract Testing — Deep Dive Review (before milestone close)

Before closing 8.9.8, conduct a focused review session covering:

**What to cover:**
- What makes a test a contract test vs a unit test vs an integration test
- How test_retrieval_api.py maps specifically to the contracts defined
  in pke/api/models/query.py — field by field, validation rule by rule
- The consumer/provider framing: Obsidian plugin is the consumer,
  the PKE API is the provider, the Pydantic models are the written contract
- How breaking changes to the contract would be caught (and which
  kinds of breaking changes would NOT be caught — the gaps)
- How this pattern maps to the ERM PRB problem — provider feeds,
  schema drift, and what contract tests at integration boundaries
  would have caught

**Why this matters beyond PKE:**
The discipline of writing tests from the consumer's point of view —
verifying that a boundary holds, not just that internal logic works —
is the methodology missing from the ERM platform. This session is
the conceptual foundation for the Citi contract testing program.
Understanding it deeply here makes it transferable there.

**Output of the session:**
A short written summary capturing the conceptual framework in plain
language — to be saved as CONTRACT_TESTING_NOTES.md — suitable for
use when presenting the methodology internally at Citi.

---

## Tech Stack

- TypeScript — Obsidian plugin language
- Obsidian Plugin API — plugin scaffolding and UI
- PKE Retrieval API (8.9.7) — must be running locally or hosted

---

## Future — Named for Design Continuity

**Temporal Reflection mode** — a distinct retrieval mode that surfaces
emotional and situational patterns across time, not just topical
similarity. The signals are already in the corpus: anxiety patterns
in language, recurring themes across years, outcomes that followed
fears that never materialized. The scoring hook (_score) in the
retriever is the right place to implement this. Requires living with
topical retrieval first to understand what temporal signal looks like
in practice. Target: 8.9.9 or dedicated 9.x milestone.

**Personal relevance scoring** — a learned layer on top of cosine
similarity, trained from thumbs up/down interactions logged in 8.9.8.
The _score() hook in retriever.py is already isolated for this.
Target: 8.9.9.

---

## Previous Milestone: 8.9.7 — COMPLETE ✅

Completed 2026-03-08. See git history and prior CURRENT_TASK.md for
full details.

---

### Session 2026-03-12
- ✅ Fixed CORS issue in pke/api/main.py — added CORSMiddleware
- ✅ Plugin fully operational — reflections surfacing in real time
- ✅ First live session with the plugin — feedback captured below

### First Live Session Observations (2026-03-12)
These observations come from the first real use of the plugin and
drive the post-launch improvement backlog:

1. Relevance ranking needs work
   Raw cosine similarity surfaces semantically related content but
   the connection is not always immediately obvious to the user.
   Expected at this stage — personal relevance scoring (8.9.9) is
   the planned solution. Capture specific cases that feel off to
   build intuition for what signals are missing.

2. Query scope needs user control
   Currently always sends last 4 lines (~500 tokens). Three modes
   needed:
       Auto      — current behaviour, last few paragraphs
       Paragraph — only the current paragraph
       Selection — user highlights text, triggers reflection query
                   from exactly that selection (most powerful mode —
                   turns the panel from ambient to intentional)
   Selection mode is a priority addition to settings UI.

3. HTML markup visible in some reflections
   Joplin export artefacts — some notes were stored with HTML
   that the parser carried through into matched_text. Fix options:
       a) Strip HTML at parse time in the chunker
       b) Strip HTML at render time in insight-view.ts
   Option (a) is cleaner — the database should never contain raw
   HTML markup. Deferred to a chunker cleanup pass.

4. Reflection panel links not working
   Navigation tries to match note_title against Obsidian vault
   files. Corpus is Joplin notes not yet migrated into Obsidian —
   no matching vault files exist. Links will work correctly after
   the Joplin → Obsidian migration (milestone 9.x). Not a bug —
   a migration dependency surfacing as expected.

---

## Next Session Start Point

### Priority 1 — Local Platform Setup
Complete the local platform setup tasks in order:
1. Ensure Joplin notes always available offline (OneDrive settings)
2. Install Ollama from ollama.com
3. Download Llama 3: ollama pull llama3
4. Verify Ollama working: ollama serve + ollama run llama3
5. Note machine specs for model variant decision

### Priority 2 — iMessage Parser
1. Export bilateral threads from iMazing:
   - Thomas <-> Patrick
   - Thomas <-> James
   - Thomas <-> Chris
   - Thomas <-> William
   Save to: C:\Users\thoma\Documents\dev\pke-data\imessage-exports\
2. Cut branch: git checkout -b feat/9.x-imessage-parser
3. Begin parser implementation

### Priority 3 — Observer Layer Milestone
Capture in roadmap — see session notes from 2026-03-15.
A frontier/local model watches the journal being written,
has been given a persistent context document about the writer,
sees what the retrieval engine surfaced, and comments on
the relationship between current writing and past history.

Update CURRENT_TASK.md timestamp at session start.
