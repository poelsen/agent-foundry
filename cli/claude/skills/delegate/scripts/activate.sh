#!/usr/bin/env bash
# .claude/skills/delegate/scripts/activate.sh
#
# Source this file from an interactive shell to enter a delegate
# environment. It sets the Anthropic *and* OpenAI env families (pointing
# both at MiniMax's native compatibility endpoints), cds into the worktree, and leaves
# you in your shell. Run `claude`, `opencode`, `aider`, or anything
# else that reads those env vars — all go to the delegate model.
#
# Usage:
#   source .claude/skills/delegate/scripts/activate.sh JOB [MODEL]
#
# Example:
#   source .claude/skills/delegate/scripts/activate.sh scrape MiniMax-M2
#   claude
#
# NOTE: must be sourced, not executed. Running directly will exit
# without effect (the env exports wouldn't survive the subshell).

# Guard: detect if executed rather than sourced.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "activate.sh: must be sourced, not executed" >&2
    echo "usage: source .claude/skills/delegate/scripts/activate.sh JOB [MODEL]" >&2
    exit 1
fi

_delegate_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$_delegate_dir/lib.sh"

_job="${1:-}"
_model="${2:-$DEFAULT_MODEL}"

if [[ -z "$_job" ]]; then
    echo "usage: source .claude/skills/delegate/scripts/activate.sh JOB [MODEL]" >&2
    return 1 2>/dev/null || true
fi

load_env || return 1
[[ -n "${MINIMAX_API_KEY:-}" ]] \
    || { echo "[delegate] ERROR: MINIMAX_API_KEY not set — add to .env" >&2; return 1; }
ensure_worktree "$_job" || return 1

_wt_path="$(worktree_path "$_job")"
# shellcheck disable=SC2046
eval $(export_env_for_shell "$_job" "$_model")

cd "$_wt_path" || return 1

log_event "\"event\":\"activate\",\"job\":\"$_job\",\"model\":\"$_model\""

cat <<BANNER >&2

  ┌─ foundry-delegate activated ─────────────────────────────
  │ job:      $_job
  │ model:    $_model
  │ backend:  $MINIMAX_ANTHROPIC_BASE
  │ cwd:      $_wt_path
  │ env set:  ANTHROPIC_* + OPENAI_* → MiniMax
  │
  │ Run: claude    opencode    aider    (anything)
  │ When done: cd back to primary and unset env vars
  │ (or just close this shell).
  └──────────────────────────────────────────────────────────

BANNER

unset _delegate_dir _job _model _wt_path
