#!/bin/bash
# Run mypy type check after editing Python files
# PostToolUse hook for Claude Code (.claude/settings.json) and Codex
# (.codex/hooks.json). Registered for every edit tool; acts on *.py only.
source "$(dirname "$0")/_edited-files.sh"

edited_files | while IFS= read -r file_path; do
  case "$file_path" in *.py) ;; *) continue ;; esac
  [ -f "$file_path" ] || continue
  if command -v mypy >/dev/null 2>&1; then
    mypy --follow-imports=skip "$file_path" 2>&1 | head -10 >&2 || true
  else
    echo "[Hook] mypy not found — install with: uv pip install mypy" >&2
  fi
done
