#!/bin/bash
# Type-check edited Python files with mypy and hand the errors back to the
# agent — only in projects that configure mypy (mypy.ini, .mypy.ini,
# [mypy] in setup.cfg or [tool.mypy] in pyproject.toml).
# PostToolUse hook for Claude Code, Codex and Antigravity; acts on *.py only.
source "$(dirname "$0")/_edited-files.sh"

problems=""
while IFS= read -r file_path; do
  case "$file_path" in *.py) ;; *) continue ;; esac
  [ -f "$file_path" ] || continue
  has_config "$file_path" mypy.ini .mypy.ini 'setup.cfg:^\[mypy' 'pyproject.toml:^\[tool\.mypy' || continue
  if command -v mypy >/dev/null 2>&1; then
    errors=$(mypy --follow-imports=skip "$file_path" 2>&1 | grep -E ': error:' | head -10)
    [ -n "$errors" ] && problems+="mypy found type errors in $file_path:"$'\n'"$errors"$'\n'
  else
    echo "[Hook] mypy not found — install with: uv pip install mypy" >&2
  fi
done < <(edited_files)
report mypy "$problems"
