# CURRENT_TASK.md
## Milestone 8.9.8 — Obsidian Insight Plugin

Last updated: 2026-03-10 19:30 EST

---

## Status: IN DESIGN

Branch to cut: feat/8.9.8-obsidian-plugin

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

Implementation note: this preference maps directly to the recency
decay function in the retriever's _score() hook. "Favour older"
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

## Next Session Start Point

1. Cut branch: git checkout -b feat/8.9.8-obsidian-plugin
2. Write deferred tests from 8.9.7 first:
   - tests/unit/test_retriever.py
   - tests/integration/test_retrieval_api.py
   - tests/unit/test_embed_chunks.py
3. Begin Obsidian plugin scaffolding (TypeScript)
4. Update CURRENT_TASK.md timestamp (ask Thomas for actual time)
