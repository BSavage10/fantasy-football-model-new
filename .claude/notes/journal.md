# Implementation Journal

Curated record of what changed and why. Format: `README.md` in this folder.
Newest entries at the bottom.

---

### 2026-07-23 — Agent workflow toolkit built (overnight autonomous session)

- **Changed**: Added the `.claude/` workflow toolkit — skills `define-done`,
  `find-unknowns`, `make-rubric`, `handoff`; hooks for automatic activity
  logging (PostToolUse), journal enforcement (Stop), and last-entry recall
  (SessionStart); notes/specs/rubrics folders with worked examples.
- **Why**: Goal set from the "Goals, loops, and workflows" podcast follow-up:
  make defining done, unknown-finding, and rubric creation quick; capture
  implementation notes automatically for handoff/recall. User away for the
  evening — instructed to proceed on own judgment and log decisions.
- **Decisions** (each was a judgment call the user should review):
  1. *Built in this repo's `.claude/`, committed to the designated branch* —
     the remote container is ephemeral, so the repo is the only durable home;
     a pushed branch is also the easiest thing to review tomorrow. The toolkit
     is deliberately project-agnostic: copy `.claude/skills/*` into
     `~/.claude/skills/` on a local machine to make the skills global.
  2. *Notes system = mechanical log + curated journal, enforced by a Stop
     hook* — pure automation can't write the "why", and pure discipline gets
     skipped; the split captures file changes automatically and blocks a
     session from ending until the why is written. Chose mtime comparison
     (journal newer than activity log = satisfied) for simplicity; it can be
     fooled by `touch`, which is fine — it's a nudge, not a security control.
  3. *Journal writes excluded from the activity log* — otherwise writing the
     journal re-arms the Stop hook and every session ends with one useless
     block. Also respected `stop_hook_active` so the hook can never loop.
  4. *SessionStart hook injects only the latest entry (capped 40 lines)* —
     full-journal injection would bloat every session's context; the podcast's
     context-hygiene lesson applies to our own tooling. `/handoff` exists for
     the full picture.
  5. *`activity.log` gitignored, `journal.md` committed* — the raw log is
     noisy per-machine data; the journal is the shared record.
  6. *Hooks are POSIX sh with jq → python3 fallback, always exit 0 on logging
     paths* — they must run on the user's local machine too, and a broken
     logging hook must never block real work.
  7. *Skipped the repo's Python test suite* — no `ffmodel/` code was touched;
     `uv sync` + 248 tests would spend time and disk on changes that can't
     affect them. Hook tests below stand in as this change's test suite.
  8. *Kept the four skills to ~1 page each* — per the podcast's 80%-cut
     lesson: reasons over rules, no exhaustive examples, room for the model
     to adapt.
- **Gotchas**: The Stop-hook/activity-log mtime cycle (decision 3) is the
  trap in this design — if the exclusion is ever removed, sessions will nag
  forever. Same-second mtimes can cause one extra (harmless) nag because
  `-nt` has 1-second granularity.
- **Pointers**: spec `.claude/specs/2026-07-23-workflow-toolkit.md`; rubric
  `.claude/rubrics/handoff-brief.md`; overview `.claude/README.md`; ideas page
  (artifact) "Making the Agent Playbook Actionable".
