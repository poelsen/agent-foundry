#!/bin/bash
# Auto-format JS/TS files with Prettier after edits
# Usage: Add as PostToolUse hook in project .claude/settings.json
# Matcher: "Edit|MultiEdit|Write"; the script itself filters *.ts, *.tsx, *.js, *.jsx
input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""')
case "$file_path" in
  *.ts|*.tsx|*.js|*.jsx) ;;
  *) echo "$input"; exit 0 ;;
esac

if [ -n "$file_path" ] && [ -f "$file_path" ]; then
  if command -v prettier >/dev/null 2>&1; then
    prettier --write "$file_path" 2>&1 | head -5 >&2
  else
    echo "[Hook] prettier not found — install with: npm install -g prettier" >&2
  fi
fi

echo "$input"
