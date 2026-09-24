#!/bin/bash
# Run cargo check after editing Rust files and hand the errors back to the
# agent. One crate-wide check per edit, however many .rs files it touched.
# PostToolUse hook for Claude Code, Codex and Antigravity; acts on *.rs only.
source "$(dirname "$0")/_edited-files.sh"

problems=""
while IFS= read -r file_path; do
  case "$file_path" in *.rs) ;; *) continue ;; esac
  [ -f "$file_path" ] || continue
  crate=$(cd "$(dirname "$file_path")" && pwd)
  while [ "$crate" != "/" ] && [ ! -f "$crate/Cargo.toml" ]; do crate=$(dirname "$crate"); done
  [ -f "$crate/Cargo.toml" ] || break
  if command -v cargo >/dev/null 2>&1; then
    errors=$(cargo check --manifest-path "$crate/Cargo.toml" --message-format=short 2>&1 \
      | grep -E '(^|: )error' | head -10)
    [ -n "$errors" ] && problems="cargo check found errors:"$'\n'"$errors"$'\n'
  else
    echo "[Hook] cargo not found — install from https://rustup.rs" >&2
  fi
  break
done < <(edited_files)
report cargo "$problems"
