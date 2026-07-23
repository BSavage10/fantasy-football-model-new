#!/bin/sh
# Stop hook: if files changed this session but journal.md has no newer entry,
# block the stop once and ask for a journal entry. Self-clearing: once the
# journal is written it is newer than the activity log, and the hook passes.
input=$(cat)

# Never loop: when Claude is already continuing because of a Stop hook,
# stop_hook_active is true and we must let it stop.
active=""
if command -v jq >/dev/null 2>&1; then
  active=$(printf '%s' "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)
elif command -v python3 >/dev/null 2>&1; then
  active=$(printf '%s' "$input" | python3 -c \
    'import sys,json;print(str(json.load(sys.stdin).get("stop_hook_active",False)).lower())' 2>/dev/null)
else
  case "$input" in *stop_hook_active*true*) active=true ;; esac
fi
[ "$active" = "true" ] && exit 0

notes="${CLAUDE_PROJECT_DIR:-.}/.claude/notes"
log="$notes/activity.log"
journal="$notes/journal.md"

# Nothing logged -> nothing to journal.
[ -s "$log" ] || exit 0
# Journal already updated after the last logged change -> all good.
if [ -f "$journal" ] && [ "$journal" -nt "$log" ]; then
  exit 0
fi

cat >&2 <<'EOF'
Implementation notes are due before stopping: files were changed this session
but .claude/notes/journal.md has no entry newer than the change log. Append a
dated entry to .claude/notes/journal.md covering: what changed and why, the
decisions made (with reasons), gotchas discovered, and pointers to any spec or
rubric files. Format: .claude/notes/README.md. Then stop.
EOF
exit 2
