#!/usr/bin/env bash
# session-id.sh — Detect current Claude session ID.
# Source this file, then use $SESSION_ID and $SHORT_ID.
#
# Detection: encode CWD the same way Claude does (/ → -, _ → -, prepend -)
# then look up the most recent .jsonl in that project directory.

SESSION_ID=""
PROJECTS_BASE="$HOME/.claude/projects"
if [[ -d "$PROJECTS_BASE" ]]; then
    # Claude's encoding: /home/rudm/my_project → -home-rudm-my-project
    CWD_ENCODED=$(pwd | sed 's|/|-|g; s|_|-|g')
    SESSION_DIR="$PROJECTS_BASE/$CWD_ENCODED"
    if [[ -d "$SESSION_DIR" ]]; then
        LATEST=$(ls -t "$SESSION_DIR"/*.jsonl 2>/dev/null | head -1)
        if [[ -n "$LATEST" ]]; then
            SESSION_ID=$(basename "$LATEST" .jsonl)
        fi
    fi
fi
SESSION_ID="${SESSION_ID:-unknown}"
SHORT_ID="${SESSION_ID:0:8}"
