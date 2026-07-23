---
name: find-unknowns
description: Surface, rank, and plan probes for the unknowns in an idea before building it. Use during brainstorming or planning, before writing an implementation plan, when the user asks "what are we missing", "what could go wrong", "poke holes in this", or proposes building something on unfamiliar ground.
---

# Find Unknowns

Planning is uncertainty reduction, not document production. Before a sizable
build: enumerate what isn't known, rank by danger, attach the cheapest probe to
each, and run the kill-test first.

## 1. Enumerate through two lenses

- **Unknowns about the want** — what would the user reject? Which qualities
  matter most? What does "good" look like — and can they only recognize it,
  not describe it? (If so, a mockup answers what a question can't.)
- **Unknowns about the system** — tool and API limits, edge cases, data
  quality and availability, performance realities, anything currently being
  trusted without having been tested.

List everything before judging anything.

## 2. Rank by danger

Two questions per unknown: *could the answer kill or reshape the approach?*
and *how expensive is discovering the answer late?* High/high goes first.
Drop unknowns that are cheap to absorb whenever they surface — not every
unknown deserves a probe.

## 3. Attach the cheapest probe that answers it

| Probe | Good for |
|---|---|
| 10-minute research or doc read | published limits, prior art |
| Explainer written by the agent | how an unfamiliar system actually works |
| Throwaway HTML mockup | preferences the user can only recognize on sight |
| Bounded spike (timeboxed throwaway code) | "does this tool handle our case" |
| Small experiment on real data | data quality, performance |

Run the probes that need no user input immediately. Queue the rest as
questions — each with your recommended default so the user can just say yes.

## 4. Kill-test first

Identify the single probe most likely to invalidate the whole approach and run
it before anything gets built. A negative result is a win: it costs an hour
instead of a week. Record negative results in `.claude/notes/journal.md` so
they aren't rediscovered the hard way.

## Output

A ranked table: **unknown · lens · danger · probe · status**. If a Done Spec
exists for this task in `.claude/specs/`, append the table to it under
`## Unknowns`; otherwise save it there as its own dated file.
