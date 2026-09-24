#!/bin/bash
# Auto-format JS/TS files with Prettier after edits — only in projects that
# configure Prettier (a .prettierrc*, prettier.config.* or "prettier" in
# package.json). PostToolUse hook for Claude Code, Codex and Antigravity;
# acts on *.ts, *.tsx, *.js, *.jsx only.
source "$(dirname "$0")/_edited-files.sh"

while IFS= read -r file_path; do
  case "$file_path" in *.ts|*.tsx|*.js|*.jsx) ;; *) continue ;; esac
  [ -f "$file_path" ] || continue
  has_config "$file_path" .prettierrc .prettierrc.json .prettierrc.json5 .prettierrc.yml \
    .prettierrc.yaml .prettierrc.toml .prettierrc.js .prettierrc.cjs .prettierrc.mjs \
    prettier.config.js prettier.config.cjs prettier.config.mjs 'package.json:"prettier"' || continue
  if command -v prettier >/dev/null 2>&1; then
    prettier --write "$file_path" 2>&1 | head -5 >&2
  else
    echo "[Hook] prettier not found — install with: npm install -g prettier" >&2
  fi
done < <(edited_files)
