#!/bin/bash
# Auto-format JS/TS files with Prettier after edits
# Usage: Add as PostToolUse hook in project .claude/settings.json
# Matcher: tool == "Edit" && tool_input.file_path matches "\\.(ts|tsx|js|jsx)$"
input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""')

if [ -n "$file_path" ] && [ -f "$file_path" ]; then
  if command -v prettier >/dev/null 2>&1; then
    prettier --write "$file_path" 2>&1 | head -5 >&2
  else
    echo "[Hook] prettier not found — install with: npm install -g prettier" >&2
  fi
fi

echo "$input"
