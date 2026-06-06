#!/bin/bash
# Run mypy type check after editing Python files
# Usage: Add as PostToolUse hook in project .claude/settings.json
# Matcher: tool == "Edit" && tool_input.file_path matches "\\.py$"
input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""')

if [ -n "$file_path" ] && [ -f "$file_path" ]; then
  if command -v mypy >/dev/null 2>&1; then
    mypy --follow-imports=skip "$file_path" 2>&1 | head -10 >&2 || true
  else
    echo "[Hook] mypy not found — install with: uv pip install mypy" >&2
  fi
fi

echo "$input"
