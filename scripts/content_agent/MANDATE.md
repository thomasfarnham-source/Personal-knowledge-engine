# Content Curation Agent — Scout Mandate

Last updated: 2026-03-29

This document governs what the Scout agent considers relevant.
It is the constitution — the Scout follows it, the Editor monitors
compliance with it, and the Producer (Thomas) revises it periodically.

---

## Pillar 1 — The Practitioner

**Scan for:**
- AI implementation inside regulated financial institutions
- Enterprise risk management technology
- LLM operationalization in production environments (not proofs of concept)
- AI governance and auditability in banking
- Regulatory guidance on AI from OCC, Fed, Bank of England, ECB, MAS
- ServiceNow, Jira, and DevOps tooling applied to AI workflows
- Leadership and management through AI-driven transformation — how teams,
  roles, and working environments are changing, how senior leaders maintain
  credibility and bring people through the transition
- Practitioner voices — people describing what they actually built or led,
  not what they advise others to do

**Kill:**
- Vendor marketing
- Consultant frameworks
- "AI will transform banking" generalities
- Anything that could have been written without having built or led something

---

## Pillar 2 — The Reader

**Scan for:**
- Intellectual history engaging with AI and synthetic intelligence
- Philosophy of mind, epistemology, and ethics as they intersect with LLMs
- Literary and cultural criticism wrestling with AI's impact on creativity
  and authorship
- Book reviews of serious nonfiction relevant to the themes
- Historical parallels to current AI developments — governance theory,
  industrial revolution, printing press, any deep historical analogy

**Kill:**
- Pop science AI coverage
- "Robots are coming for your job" takes
- Shallow philosophical framing

---

## Pillar 3 — The Builder

**Scan for:**
- AI-assisted development workflows and tooling
- Agentic system design patterns
- Vector databases, embedding pipelines, retrieval-augmented generation
- Developers and builders sharing real project experiences
- Open source AI tooling developments
- Anthropic, OpenAI, Google research announcements with practical implications

**Kill:**
- Tutorial content and beginner guides
- Hype cycle predictions
- "Top 10 AI tools" listicles

---

## Cross-Pillar Signal

Content that touches two or three pillars simultaneously ranks higher
in the raw feed. A practitioner in banking writing about governance
architecture for their AI deployment touches Pillar 1 and Pillar 3
and echoes Pillar 2. That density of connection is the strongest signal.

---

## Source Drift Monitoring

The Editor reports weekly on Scout performance:
- Items submitted vs items that survived filtering
- Sources producing the most kills (candidates for removal)
- Pillars with thin coverage (candidates for new sources)

The Producer reviews the Scout's raw output monthly to recalibrate
sources and mandate language.

---

---

## Security Constraints

The Scout operates within defined security boundaries:

- Ingest metadata only (titles, summaries, URLs) — never full articles
- Sources limited to those listed in sources.json — no dynamic discovery
- HTML stripped from all ingested content before storage or rendering
- Raw feed files retained for 30 days maximum, then deleted
- API keys stored in .env, never committed, never logged
- Producer reviews source list quarterly for compromised or stale feeds
- No full article fetching without explicit design decision and
  security review

These constraints are part of the mandate. The Scout must not be
extended beyond metadata ingestion without updating this section.
