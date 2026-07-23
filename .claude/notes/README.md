# Implementation Notes

Two files, two jobs:

- **`journal.md`** — the curated record. One dated entry per work session that
  changed anything. Written by the session that did the work; a Stop hook
  blocks ending a session with unjournaled changes. Committed to git.
- **`activity.log`** — the raw machine trail, appended automatically by a
  PostToolUse hook on every file write. Gitignored; useful for filling gaps,
  never the narrative.

Recall happens two ways: a SessionStart hook injects the latest entry into
every new session's context, and the `/handoff` skill builds a full catch-up
brief on demand.

## Journal entry format

Newest entries at the **bottom** (append-only; the SessionStart hook reads the
last `### ` heading).

```markdown
### YYYY-MM-DD — one-line summary
- **Changed**: what was added/modified, at the level of capabilities not files
- **Why**: the need or request behind it
- **Decisions**: choice made — and the reason, so it isn't relitigated blind
- **Gotchas**: anything that surprised, failed first, or will bite later
- **Pointers**: relevant specs, rubrics, PRs, artifacts
```

Keep entries under ~20 lines. Decisions and gotchas are the valuable part —
"what changed" is recoverable from git, the *why* is not.
