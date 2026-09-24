#!/bin/bash
# Run TypeScript check after editing TS files
# Usage: Add as PostToolUse hook in project .claude/settings.json
# Matcher: "Edit|MultiEdit|Write"; the script itself filters *.ts, *.tsx
input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""')
case "$file_path" in
  *.ts|*.tsx) ;;
  *) echo "$input"; exit 0 ;;
esac

if [ -n "$file_path" ] && [ -f "$file_path" ]; then
  dir=$(dirname "$file_path")
  project_root="$dir"
  while [ "$project_root" != "/" ] && [ ! -f "$project_root/package.json" ]; do
    project_root=$(dirname "$project_root")
  done

  if [ -f "$project_root/tsconfig.json" ]; then
    cd "$project_root" && npx tsc --noEmit --pretty false 2>&1 | grep "$file_path" | head -10 >&2 || true
  fi
fi

echo "$input"
