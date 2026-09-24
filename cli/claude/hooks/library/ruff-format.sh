#!/bin/bash
# Auto-format Python files with ruff after edits
# Usage: Add as PostToolUse hook in project .claude/settings.json
# Matcher: "Edit|MultiEdit|Write"; the script itself filters *.py
input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""')
case "$file_path" in
  *.py) ;;
  *) echo "$input"; exit 0 ;;
esac

if [ -n "$file_path" ] && [ -f "$file_path" ]; then
  if command -v ruff >/dev/null 2>&1; then
    ruff format "$file_path" 2>&1 | head -5 >&2
  else
    echo "[Hook] ruff not found — install with: uv pip install ruff" >&2
  fi
fi

echo "$input"
