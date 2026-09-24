#!/bin/bash
# Type-check edited TS files with the project's own TypeScript compiler and
# hand the errors for those files back to the agent — only inside a project
# with tsconfig.json and a local typescript install (npx --no-install never
# downloads a package). PostToolUse hook for Claude Code, Codex and
# Antigravity; acts on *.ts, *.tsx only.
source "$(dirname "$0")/_edited-files.sh"

problems=""
while IFS= read -r file_path; do
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
    errors=$(cd "$project_root" && npx --no-install tsc --noEmit --pretty false 2>&1 \
      | grep -F "$rel_path" | head -10)
    [ -n "$errors" ] && problems+="tsc found type errors in $rel_path:"$'\n'"$errors"$'\n'
  fi
done < <(edited_files)
report tsc "$problems"
