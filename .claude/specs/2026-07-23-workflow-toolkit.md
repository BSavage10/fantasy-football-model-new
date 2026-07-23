# Done Spec: Agent workflow toolkit

*(This is the spec for the toolkit build itself — kept as a real, worked
example of the format.)*

- **Outcome**: A committed, pushed `.claude/` toolkit giving this project (and,
  by copy, any project) four capabilities: quick done-definitions, integrated
  unknown-finding, fast rubric creation, and automatic implementation-note
  capture with recall.
- **Done when**:
  - Skills `define-done`, `find-unknowns`, `make-rubric`, `handoff` exist with
    valid frontmatter.
  - Hooks `log-activity.sh`, `require-notes.sh`, `recall-on-start.sh` pass a
    shell syntax check and behave correctly on synthetic hook input: logging
    appends a line, the Stop hook blocks (exit 2) when the journal is stale,
    passes (exit 0) when the journal is fresh or `stop_hook_active` is true,
    and SessionStart prints the latest journal entry.
  - `settings.json` is valid JSON wiring all three hooks.
  - `journal.md` carries tonight's entry including every judgment call and its
    reason.
  - All of it is committed and pushed to `claude/podcast-summary-actionable-kq1nqm`.
- **Judged by**: the mechanical checks above (deterministic), plus rubric:
  `handoff-brief` for the catch-up summary left in chat.

## Unknowns

| Unknown | Lens | Danger | Probe | Status |
|---|---|---|---|---|
| Does the Stop hook loop when writing the journal itself triggers the activity log? | system | high — would make every session unstoppable | trace the mtime cycle by hand before wiring | resolved: journal writes excluded from the log, and `stop_hook_active` is respected |
| Are `jq`/`python3` available on the user's local machine? | system | medium — hooks silently dead | can't test tonight; mitigate instead | mitigated: jq → python3 fallback; logging degrades to no-op, never blocks |
| Where should the toolkit live so it survives and gets reviewed? | want | high — wrong place means lost work | none needed; environment facts decide | resolved: repo `.claude/` on the designated branch (see journal decision 1) |
