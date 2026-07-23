#!/bin/sh
# PostToolUse hook (Write|Edit|NotebookEdit): append one line per file change
# to .claude/notes/activity.log. Mechanical capture only — the curated record
# lives in journal.md. Must never block or fail a tool call: always exits 0.
dir="${CLAUDE_PROJECT_DIR:-.}/.claude/notes"
mkdir -p "$dir" 2>/dev/null || exit 0
input=$(cat)

line=""
if command -v jq >/dev/null 2>&1; then
  line=$(printf '%s' "$input" | jq -r \
    '"\(.tool_name // "?")\t\(.tool_input.file_path // .tool_input.notebook_path // "?")"' \
    2>/dev/null)
elif command -v python3 >/dev/null 2>&1; then
  line=$(printf '%s' "$input" | python3 -c '
import sys, json
d = json.load(sys.stdin)
i = d.get("tool_input") or {}
p = i.get("file_path") or i.get("notebook_path") or "?"
print(d.get("tool_name", "?") + "\t" + p)' 2>/dev/null)
fi
[ -n "$line" ] || exit 0

# Journal/log edits are excluded, otherwise writing notes would make the log
# newer than the journal and re-trigger the Stop hook forever.
case "$line" in
  */.claude/notes/*) exit 0 ;;
esac

printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$line" >> "$dir/activity.log" 2>/dev/null
exit 0
