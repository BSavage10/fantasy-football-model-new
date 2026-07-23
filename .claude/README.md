# Agent Workflow Toolkit

Project-agnostic tooling that makes agent handoffs systematic. Four skills, three
hooks, one notes system. Nothing here knows anything about fantasy football — the
whole directory can be copied into any other project (or the skills into
`~/.claude/skills/` to make them available everywhere).

## Skills (invoke with `/name`, or Claude triggers them from context)

| Skill | Job | Output |
|---|---|---|
| `define-done` | Turn a task into a 3-line Done Spec: Outcome / Done when / Judged by | `.claude/specs/<date>-<slug>.md` |
| `find-unknowns` | Enumerate + rank unknowns, attach the cheapest probe to each, kill-test first | `## Unknowns` section in the spec |
| `make-rubric` | Rejection-first rubric + fresh-agent verifier prompt for subjective work | `.claude/rubrics/<type>.md` |
| `handoff` | Catch-up brief from the journal, git history, and active specs | one-page brief in chat |

## Hooks (wired in `settings.json`, run automatically)

| Hook | Event | What it does |
|---|---|---|
| `log-activity.sh` | PostToolUse (Write/Edit/NotebookEdit) | Appends a timestamped line per file change to `.claude/notes/activity.log`. Silent, mechanical, never blocks. |
| `require-notes.sh` | Stop | If files changed this session but `journal.md` has no newer entry, blocks the stop once and asks for a journal entry. Self-clears once the entry is written. |
| `recall-on-start.sh` | SessionStart | Prints the most recent journal entry into the new session's context, so every session starts knowing where the last one left off. |

## The notes system

`.claude/notes/journal.md` is the curated record (what changed, why, decisions,
gotchas); `activity.log` is the raw machine trail (gitignored). Format and
conventions: `.claude/notes/README.md`.

## Design principles

- **Reasons over rules.** Skills explain why, so the model can make sound
  exceptions instead of following fake absolutes.
- **Lean context.** Each skill is a page, not a manual. Trim further as models
  improve.
- **Self-clearing enforcement.** The Stop hook nags exactly until the journal is
  written, then gets out of the way. It never loops (it respects
  `stop_hook_active`) and journal edits themselves are excluded from the
  activity log so writing notes can't re-trigger the nag.
