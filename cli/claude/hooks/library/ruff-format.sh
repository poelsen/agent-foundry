#!/bin/bash
# Auto-format Python files with ruff after edits — only in projects that
# format with ruff (a [format] section in ruff.toml/.ruff.toml, [tool.ruff.format]
# in pyproject.toml, or a ruff-format pre-commit hook) and never where black
# is configured (pyproject or pre-commit), so lint-only ruff users and black
# or unformatted projects are left alone.
# PostToolUse hook for Claude Code, Codex and Antigravity; acts on *.py only.
source "$(dirname "$0")/_edited-files.sh"

while IFS= read -r file_path; do
  case "$file_path" in *.py) ;; *) continue ;; esac
  [ -f "$file_path" ] || continue
  has_config "$file_path" 'pyproject.toml:^\[tool\.black' \
    '.pre-commit-config.yaml:id:[[:space:]]*black([[:space:]]|$)' && continue
  has_config "$file_path" 'ruff.toml:^(\[format\]|format\.)' '.ruff.toml:^(\[format\]|format\.)' \
    'pyproject.toml:^\[tool\.ruff\.format' \
    '.pre-commit-config.yaml:id:[[:space:]]*ruff-format' || continue
  if command -v ruff >/dev/null 2>&1; then
    ruff format "$file_path" 2>&1 | head -5 >&2
  else
    echo "[Hook] ruff not found — install with: uv pip install ruff" >&2
  fi
done < <(edited_files)
