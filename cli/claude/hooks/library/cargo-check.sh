#!/bin/bash
# Run cargo check after editing Rust files
# Usage: Add as PostToolUse hook in project .claude/settings.json
# Matcher: "Edit|MultiEdit|Write"; the script itself filters *.rs
input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""')
case "$file_path" in
  *.rs) ;;
  *) echo "$input"; exit 0 ;;
esac

if [ -n "$file_path" ] && [ -f "$file_path" ]; then
  if command -v cargo >/dev/null 2>&1; then
    cargo check --message-format=short 2>&1 | head -10 >&2 || true
  else
    echo "[Hook] cargo not found — install from https://rustup.rs" >&2
  fi
fi

echo "$input"
