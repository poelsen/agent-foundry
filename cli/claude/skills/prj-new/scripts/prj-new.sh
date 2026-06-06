#!/usr/bin/env bash
# prj-start.sh — Create a new project file.
set -euo pipefail

PRJ_NAME="${1:-}"

if [[ -z "$PRJ_NAME" ]]; then
    echo "Usage: /prj-start <name>"
    echo "Name must be lowercase alphanumeric with hyphens (e.g. 'bank', 'auth-refactor')."
    exit 1
fi

if ! [[ "$PRJ_NAME" =~ ^[a-z0-9-]+$ ]]; then
    echo "Error: name must match [a-z0-9-]+ (got '$PRJ_NAME')"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PRJS_DIR="$PROJECT_ROOT/.claude/prjs"
PRJ_FILE="$PRJS_DIR/$PRJ_NAME.md"
NOW=$(date +%Y-%m-%dT%H:%M)

# shellcheck source=../../_lib/session-id.sh
source "$PROJECT_ROOT/.claude/skills/_lib/session-id.sh"

mkdir -p "$PRJS_DIR"

if [[ -f "$PRJ_FILE" ]]; then
    echo "ERROR: Project '$PRJ_NAME' already exists."
    echo "Use /prj-resume $PRJ_NAME to resume it."
    exit 1
fi

if [[ "$SESSION_ID" == "unknown" ]]; then
    RESUME_LINE="**Session:** Run \`claude --resume\` to pick from recent sessions"
    FORK_LINE=""
else
    RESUME_LINE="**Session:** \`claude --resume $SHORT_ID\`"
    FORK_LINE=$'\n'"**Fork:** \`claude --fork-session --resume $SHORT_ID\`"
fi

cat > "$PRJ_FILE" << EOF
---
name: $PRJ_NAME
status: active
created: $NOW
updated: $NOW
session_id: $SESSION_ID
---

# $PRJ_NAME

## Goal
<!-- Fill: what this project is about -->

## Status
<!-- Fill: current state -->

## Decisions
<!-- Fill: key decisions made -->

## Key Files
<!-- Fill: important files for this project -->

## Resume
$RESUME_LINE$FORK_LINE
**Last action:** <!-- Fill -->
**Next step:** <!-- Fill -->
EOF

echo "ACTION=created"
echo "PRJ_FILE=$PRJ_FILE"
echo "SESSION_ID=$SESSION_ID"
echo "SHORT_ID=$SHORT_ID"
echo "DATE=$NOW"

if [[ "$SESSION_ID" != "unknown" ]]; then
    echo "Resume: claude --resume $SHORT_ID"
fi
