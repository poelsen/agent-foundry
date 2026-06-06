#!/usr/bin/env bash
# prj-pause.sh — Update a project file with session metadata, set status to paused.
set -euo pipefail

PRJ_NAME="${1:-}"

if [[ -z "$PRJ_NAME" ]]; then
    echo "Usage: /prj-pause <name>"
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

if [[ ! -f "$PRJ_FILE" ]]; then
    echo "ERROR: Project '$PRJ_NAME' not found."
    echo "Use /prj-new $PRJ_NAME to create it first."
    if ls "$PRJS_DIR"/*.md &>/dev/null; then
        echo ""
        echo "Available projects:"
        for f in "$PRJS_DIR"/*.md; do
            echo "  - $(basename "$f" .md)"
        done
    fi
    exit 1
fi

# Update frontmatter
sed -i "s/^updated:.*$/updated: $NOW/" "$PRJ_FILE"
sed -i "s/^status:.*$/status: paused/" "$PRJ_FILE"

# Only overwrite session_id if we detected a real one
if [[ "$SESSION_ID" != "unknown" ]]; then
    sed -i "s/^session_id:.*$/session_id: $SESSION_ID/" "$PRJ_FILE"
fi

echo "ACTION=updated"
echo "PRJ_FILE=$PRJ_FILE"
echo "SESSION_ID=$SESSION_ID"
echo "SHORT_ID=$SHORT_ID"
echo "DATE=$NOW"

if [[ "$SESSION_ID" != "unknown" ]]; then
    echo "Resume: claude --resume $SHORT_ID"
    echo "Fork:   claude --fork-session --resume $SHORT_ID"
else
    echo "Session ID: unknown (existing session_id preserved)"
fi
