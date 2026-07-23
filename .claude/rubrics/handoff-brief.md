# Rubric: handoff brief

For catch-up briefs produced by the `/handoff` skill (or any "where were we"
summary). Created as the toolkit's worked example of the rubric format.

| Criterion | Pass bar | Reject if | Tier |
|---|---|---|---|
| Current-state first | The first section says what works, what's in flight, and what's broken — before any history. | Reader must scroll past narrative to learn the present state. | gate |
| Decisions carry reasons | Every decision listed includes the why in the same line or sentence. | Any bare decision ("we chose X") with no reason attached. | gate |
| Pointers resolve | Every referenced spec, rubric, file, or PR is named by real path or number. | Any "see the spec" without saying which file. | quality |
| One page | The whole brief fits in roughly 40 lines / one screen. | Reader has to skim to find the actionable part. | quality |
| Next steps are startable | Each next step is concrete enough to begin without asking a question first. | Steps like "continue the work" or "improve quality". | gate |

## Verifier prompt

```text
You are verifying a deliverable against a rubric. You did not create it;
judge only what is in front of you.

<rubric>
1. Current-state first (gate): first section states what works / in flight /
   broken, before any history. Fail if narrative comes first.
2. Decisions carry reasons (gate): every decision includes its why. Fail on
   any bare decision.
3. Pointers resolve (quality): every referenced artifact is named by real
   path or number. Fail on vague references.
4. One page (quality): ~40 lines max. Fail if the actionable part must be
   hunted for.
5. Next steps are startable (gate): each step can begin without a clarifying
   question. Fail on vague steps.
</rubric>

<deliverable>
[paste the brief]
</deliverable>

For each criterion: pass or fail, with one line of evidence drawn from the
deliverable itself. Then an overall verdict: accept | revise (list the
specific fixes) | reject (say why it is unsalvageable).
Do not soften failures. A criterion without evidence of passing fails.
```
