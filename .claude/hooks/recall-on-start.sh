#!/bin/sh
# SessionStart hook: print the most recent journal entry so every new session
# begins knowing where the last one left off. Output is added to context.
journal="${CLAUDE_PROJECT_DIR:-.}/.claude/notes/journal.md"
[ -f "$journal" ] || exit 0

echo "Most recent implementation-journal entry (.claude/notes/journal.md; run /handoff for the full picture):"
# Print from the last "### " heading to end of file, capped at 40 lines.
awk '/^### /{n=NR} {l[NR]=$0} END{if (n) for (i=n; i<=NR; i++) print l[i]}' \
  "$journal" 2>/dev/null | head -40
exit 0
