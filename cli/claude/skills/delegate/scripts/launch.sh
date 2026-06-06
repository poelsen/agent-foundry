#!/usr/bin/env bash
# .claude/skills/delegate/scripts/launch.sh
#
# Interactive delegate launch. Sets up worktree + proxy + env, then execs
# `claude` in the worktree. The current terminal becomes the secondary
# Claude Code session; quitting returns to the primary shell.
#
# Usage:
#   launch.sh --job NAME [--model M]
#
#   Prefer activate.sh if you want to stay in an operator shell and run
#   arbitrary commands (claude, opencode, aider, bash) against the proxy.

set -euo pipefail
DELEGATE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DELEGATE_DIR/lib.sh"

job=""
model=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --job)    job="${2:?}";  shift 2 ;;
        --model)   model="${2:?}"; shift 2 ;;
        -h|--help) sed -n '1,16p' "$0"; exit 0 ;;
        *)         die "unknown arg: $1" ;;
    esac
done
[[ -n "$job" ]] || die "--job is required"
model="${model:-$DEFAULT_MODEL}"

load_env
require_env MINIMAX_API_KEY
ensure_worktree "$job"

wt_path="$(worktree_path "$job")"
eval "$(export_env_for_shell "$job" "$model")"

info "entering interactive secondary: job=$job model=$model"
info "worktree: $wt_path"
info "exit the secondary with Ctrl+D or /quit to return to your primary shell."
log_event "\"event\":\"launch\",\"job\":\"$job\",\"model\":\"$model\",\"mode\":\"interactive\""

cd "$wt_path"
exec claude
