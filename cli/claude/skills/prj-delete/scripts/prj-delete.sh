#!/usr/bin/env bash
# prj-delete.sh — Delete a project file.
set -euo pipefail

PRJ_NAME="${1:-}"

if [[ -z "$PRJ_NAME" ]]; then
    echo "Usage: /prj-delete <name>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PRJ_FILE="$PROJECT_ROOT/.claude/prjs/$PRJ_NAME.md"

if [[ ! -f "$PRJ_FILE" ]]; then
    echo "Project '$PRJ_NAME' not found."
    if ls "$PROJECT_ROOT/.claude/prjs/"*.md &>/dev/null; then
        echo ""
        echo "Available projects:"
        for f in "$PROJECT_ROOT/.claude/prjs/"*.md; do
            echo "  - $(basename "$f" .md)"
        done
    fi
    exit 1
fi

rm "$PRJ_FILE"
echo "Project '$PRJ_NAME' deleted."
