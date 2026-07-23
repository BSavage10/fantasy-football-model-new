---
name: define-done
description: Turn a task into a three-line Done Spec (Outcome / Done when / Judged by) before work starts. Use whenever a nontrivial task is handed off — especially autonomous or long-running work — or when the user says "define done", "spec this out", or gives a vague deliverable. Skip it for trivial edits.
---

# Define Done

Produce a Done Spec in under a minute. Draft it yourself from what the user
said — don't interview them. Ask at most one question, and only if a genuinely
open choice would change the spec; otherwise pick the sensible default and note
it in the spec.

## The spec — three lines

- **Outcome** — the artifact or state that must exist when work is finished,
  named concretely. "A passing `/export` endpoint that returns CSV", not
  "export works".
- **Done when** — exit conditions checkable without asking a human. Every
  condition should be verifiable by running something or looking at something.
- **Judged by** — the evaluation signal. Deterministic if one exists; otherwise
  write `rubric: <name>` and create it with the make-rubric skill.

## Prefer deterministic signals

Work down this list and take the first that fits — only fall back to a rubric
when nothing above it applies:

1. A test that fails before the change and passes after
2. Build, lint, or type check passes
3. A measurable number crosses a threshold (latency, size, count, score)
4. Output compared against a source of truth (design file, schema, fixture)
5. Rubric scored by a fresh verifier agent (subjective work)

A vague target wastes persistence: an agent can work for hours in the wrong
direction if "done" isn't pinned. That's why the spec comes before the work,
not after.

## Sharpen with the rejection test

Ask: *what result would make the user reject this even though it technically
satisfies the request?* Every answer becomes another **Done when** condition.

## Save and go

Save to `.claude/specs/YYYY-MM-DD-<slug>.md`, echo the three lines in the
conversation, then start the work. The spec is the contract that the journal
entry and any verifier agent refer back to. If the task has meaningful
uncertainty, run the find-unknowns skill against the spec before building.
