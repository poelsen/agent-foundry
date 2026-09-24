#!/bin/bash
# Run cargo check after editing Rust files
# PostToolUse hook for Claude Code (.claude/settings.json) and Codex
# (.codex/hooks.json). Registered for every edit tool; acts on *.rs only,
# running one crate-wide check however many .rs files the edit touched.
source "$(dirname "$0")/_edited-files.sh"

edited_files | while IFS= read -r file_path; do
  case "$file_path" in *.rs) ;; *) continue ;; esac
  [ -f "$file_path" ] || continue
  if command -v cargo >/dev/null 2>&1; then
    cargo check --message-format=short 2>&1 | head -10 >&2 || true
  else
    echo "[Hook] cargo not found — install from https://rustup.rs" >&2
  fi
  break
done
