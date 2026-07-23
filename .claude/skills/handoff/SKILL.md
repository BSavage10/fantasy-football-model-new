---
name: handoff
description: Produce a catch-up brief from the implementation journal and git history. Use when the user asks "where were we", "catch me up", "what changed", when resuming work after a gap, or before pausing a large piece of work for later pickup by a human or another session.
---

# Handoff

Reconstruct working context so the next session — or the user — starts warm
instead of re-discovering everything.

## Sources, in order

1. `.claude/notes/journal.md` — the curated record: what changed, why,
   decisions, gotchas. Read the newest entries first.
2. `git log` since the last journal entry — anything that happened but wasn't
   journaled yet.
3. `.claude/specs/` and `.claude/rubrics/` — the active contracts for
   in-flight work.
4. `.claude/notes/activity.log` — the raw file-touch trail. Use it only to
   fill gaps, never as the narrative.

## The brief — one page maximum

- **State** — what works now, what's in flight, what's broken.
- **Decisions that constrain what's next** — each with its why, so nothing
  gets relitigated blind.
- **Open unknowns** — anything flagged but unresolved.
- **Next steps** — concrete and ordered, with pointers to the relevant spec or
  rubric files.

Journal entries are evidence, not truth: where the journal and the code
disagree, trust the code and note the discrepancy in the brief.
