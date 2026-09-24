#!/bin/bash
# Run TypeScript check after editing TS files
# PostToolUse hook for Claude Code (.claude/settings.json) and Codex
# (.codex/hooks.json). Registered for every edit tool; acts on *.ts, *.tsx only.
source "$(dirname "$0")/_edited-files.sh"

edited_files | while IFS= read -r file_path; do
  case "$file_path" in *.ts|*.tsx) ;; *) continue ;; esac
  [ -f "$file_path" ] || continue
  abs_path="$(cd "$(dirname "$file_path")" && pwd)/$(basename "$file_path")"
  project_root=$(dirname "$abs_path")
  while [ "$project_root" != "/" ] && [ ! -f "$project_root/package.json" ]; do
    project_root=$(dirname "$project_root")
  done

  if [ -f "$project_root/tsconfig.json" ]; then
    # tsc reports paths relative to the project root
    rel_path="${abs_path#"$project_root"/}"
    (cd "$project_root" && npx tsc --noEmit --pretty false 2>&1 | grep -F "$rel_path" | head -10 >&2 || true)
  fi
done
