#!/usr/bin/env bash
# skills/delegate/scripts/lib.sh (deployed: .claude/skills/delegate/scripts/lib.sh)
#
# Shared helpers for the foundry-delegate scripts. Source from entry
# scripts (run.sh, launch.sh, activate.sh, worktree.sh). Do not run
# this file directly.

# Don't `set -e` here — callers decide. Do enable nounset + pipefail
# for the functions so shadowed vars and broken pipelines fail loudly.
set -uo pipefail

# Define error helpers first so REPO_ROOT check below can use die().
die()  { printf '[delegate] ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '[delegate] %s\n'        "$*" >&2; }

DELEGATE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# REPO_ROOT is the git repo of the INVOKING cwd (target project), not of
# the script's location. This lets the deployed scripts at e.g.
# $TARGET/.claude/skills/delegate/scripts/ operate on any project the
# user cd-s into before invocation.
REPO_ROOT="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)" \
    || die "not inside a git repository (cwd=$PWD) — cd into the target project first"
REPO_NAME="$(basename "$REPO_ROOT")"

# Runtime state lives under <repo>/.delegate/ — gitignored, separate
# from foundry's install machinery in <repo>/.foundry/.
DELEGATE_STATE_DIR="$REPO_ROOT/.delegate"
DELEGATE_LOG="$DELEGATE_STATE_DIR/log.jsonl"

# Backend endpoints. MiniMax hosts official Anthropic- and OpenAI-
# compatible shims, so no local proxy (ccr / LiteLLM) is needed — we
# just point Claude Code (and opencode/aider/curl) straight at them.
# Override via env if you ever want to route somewhere else.
MINIMAX_ANTHROPIC_BASE="${FOUNDRY_DELEGATE_ANTHROPIC_BASE:-https://api.minimax.io/anthropic}"
MINIMAX_OPENAI_BASE="${FOUNDRY_DELEGATE_OPENAI_BASE:-https://api.minimax.io/v1}"

DEFAULT_MODEL="${FOUNDRY_DELEGATE_DEFAULT_MODEL:-MiniMax-M2.7}"

# Load repo-root .env (and the script-dir .env if present) into the environment.
# Safe to call multiple times — `set -a` exports everything sourced.
load_env() {
    local f
    set -a
    for f in "$REPO_ROOT/.env" "$DELEGATE_DIR/.env"; do
        # shellcheck disable=SC1090
        [[ -f "$f" ]] && source "$f"
    done
    set +a
}

require_env() {
    local var="$1"
    [[ -n "${!var:-}" ]] || die "missing env var: $var (check $REPO_ROOT/.env or $DELEGATE_DIR/.env)"
}

# ── Worktree ──────────────────────────────────────────────────────────

worktree_path()   { local job="${1:?job required}"; printf '%s/%s-delegate-%s' "$(dirname "$REPO_ROOT")" "$REPO_NAME" "$job"; }
worktree_branch() { local job="${1:?job required}"; printf 'delegate/%s' "$job"; }

ensure_worktree() {
    local job="${1:?job required}"
    local wt_path branch
    wt_path="$(worktree_path "$job")"
    branch="$(worktree_branch "$job")"

    if [[ -d "$wt_path/.git" || -f "$wt_path/.git" ]]; then
        info "worktree exists: $wt_path"
        return 0
    fi

    info "creating worktree: $wt_path (branch $branch)"
    ( cd "$REPO_ROOT"
      if git show-ref --verify --quiet "refs/heads/$branch"; then
          git worktree add "$wt_path" "$branch" >&2
      else
          git worktree add -b "$branch" "$wt_path" >&2
      fi
    )
}

# ── Env export ────────────────────────────────────────────────────────

# Print shell-exportable env for a delegate session. Points Claude Code
# (Anthropic family) and OpenAI-compat tools (opencode/aider/curl) at
# MiniMax's native compatibility endpoints. MINIMAX_API_KEY must be
# loaded into the environment before this is called (see load_env).
export_env_for_shell() {
    local job="${1:?job required}"
    local model="${2:-$DEFAULT_MODEL}"
    [[ -n "${MINIMAX_API_KEY:-}" ]] \
        || die "MINIMAX_API_KEY not set — put it in $REPO_ROOT/.env (or $DELEGATE_DIR/.env) and call load_env first"
    cat <<EOF
export ANTHROPIC_BASE_URL="$MINIMAX_ANTHROPIC_BASE"
export ANTHROPIC_AUTH_TOKEN="$MINIMAX_API_KEY"
export ANTHROPIC_MODEL="$model"
export ANTHROPIC_DEFAULT_SONNET_MODEL="$model"
export ANTHROPIC_DEFAULT_OPUS_MODEL="$model"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="$model"
export API_TIMEOUT_MS="3000000"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"
export OPENAI_BASE_URL="$MINIMAX_OPENAI_BASE"
export OPENAI_API_KEY="$MINIMAX_API_KEY"
export FOUNDRY_DELEGATE_JOB="$job"
export FOUNDRY_DELEGATE_MODEL="$model"
EOF
}

# ── Logging ───────────────────────────────────────────────────────────

# Append a JSON row to the delegate log. Caller passes a JSON object body
# (no braces, no leading/trailing comma) — ts is added automatically.
# Example:  log_event '"event":"start","job":"scrape","model":"MiniMax-M2.7"'
log_event() {
    local body="${1:-}"
    local ts; ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    mkdir -p "$DELEGATE_STATE_DIR"
    if [[ -n "$body" ]]; then
        printf '{"ts":"%s",%s}\n' "$ts" "$body" >>"$DELEGATE_LOG"
    else
        printf '{"ts":"%s"}\n' "$ts" >>"$DELEGATE_LOG"
    fi
}

# JSON-encode a string (for embedding in log rows / output). Uses python3
# to avoid reimplementing escape rules in shell.
json_str() {
    python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()), end="")'
}
