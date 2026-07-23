---
name: make-rubric
description: Create a rejection-first rubric plus a fresh-agent verifier prompt for subjective or non-deterministic deliverables. Use when quality can't be checked mechanically (writing, design, summaries, "make it clean/good/polished"), when a Done Spec says "rubric", or when the user asks for review criteria.
---

# Make a Rubric

A rubric turns "make it good" into criteria a verifier can score. Build it
from rejection, not aspiration: what would make the user send this back?

## Writing the criteria

4–6 criteria. Each gets:

- **Name** — two or three words.
- **Pass bar** — one sentence describing an *observable* property. "Every
  claim links to a source", not "accurate". "No horizontal scroll at 375px",
  not "responsive".
- **Reject if** — the concrete failure that fails this criterion.
- **Tier** — `gate` (failing any gate fails the deliverable) or `quality`
  (drives the revise/accept call).

Derive criteria from: what the user has praised or rejected before, the
deliverable's actual job for its audience, and the known failure modes of this
kind of artifact. If a criterion can't be stated as something observable, it
isn't a criterion yet — decompose it until it is.

## Verification protocol

The creator never grades its own work: a model is measurably more forgiving of
output it produced (self-referential bias). Score with a **fresh agent** given
only the rubric and the deliverable — none of the creation context. Verdict
format: per-criterion pass/fail with one line of evidence, then an overall
call — `accept`, `revise` (with the specific fixes), or `reject`.

## Save and reuse

Save to `.claude/rubrics/<deliverable-type>.md` with the verifier prompt
filled in (template below). Before writing a new rubric, check that folder —
refining an existing rubric beats forking a near-duplicate. Rubrics improve by
editing after real use: when the user rejects something the rubric passed,
that's a missing criterion — add it.

## Verifier prompt template

```text
You are verifying a deliverable against a rubric. You did not create it;
judge only what is in front of you.

<rubric>
[criteria]
</rubric>

<deliverable>
[content or file reference]
</deliverable>

For each criterion: pass or fail, with one line of evidence drawn from the
deliverable itself. Then an overall verdict: accept | revise (list the
specific fixes) | reject (say why it is unsalvageable).
Do not soften failures. A criterion without evidence of passing fails.
```
