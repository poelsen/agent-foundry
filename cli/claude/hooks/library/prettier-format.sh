#!/bin/bash
# Auto-format JS/TS files with Prettier after edits
# PostToolUse hook for Claude Code (.claude/settings.json) and Codex
# (.codex/hooks.json). Registered for every edit tool; acts on
# *.ts, *.tsx, *.js, *.jsx only.
source "$(dirname "$0")/_edited-files.sh"

edited_files | while IFS= read -r file_path; do
  case "$file_path" in *.ts|*.tsx|*.js|*.jsx) ;; *) continue ;; esac
  [ -f "$file_path" ] || continue
  if command -v prettier >/dev/null 2>&1; then
    prettier --write "$file_path" 2>&1 | head -5 >&2
  else
    echo "[Hook] prettier not found — install with: npm install -g prettier" >&2
  fi
done
