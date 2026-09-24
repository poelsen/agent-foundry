#!/bin/bash
# Auto-format Python files with ruff after edits
# PostToolUse hook for Claude Code (.claude/settings.json) and Codex
# (.codex/hooks.json). Registered for every edit tool; acts on *.py only.
source "$(dirname "$0")/_edited-files.sh"

edited_files | while IFS= read -r file_path; do
  case "$file_path" in *.py) ;; *) continue ;; esac
  [ -f "$file_path" ] || continue
  if command -v ruff >/dev/null 2>&1; then
    ruff format "$file_path" 2>&1 | head -5 >&2
  else
    echo "[Hook] ruff not found — install with: uv pip install ruff" >&2
  fi
done
