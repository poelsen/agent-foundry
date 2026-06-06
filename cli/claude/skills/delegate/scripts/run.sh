#!/usr/bin/env bash
# .claude/skills/delegate/scripts/run.sh
#
# Orchestrated (non-interactive) delegate run. Primary Claude invokes this
# via Bash; the script sets up the worktree + proxy, executes `claude
# --print "$task"` in the secondary environment, auto-commits resulting
# changes on the delegate branch, and emits a JSON summary to stdout.
#
# Usage:
#   run.sh --job NAME --task "DESC" [--model M] [--timeout S] [--read-only]
#
# Required:
#   --job NAME           job label (used for worktree name + log tag)
#   --task "DESC"        self-contained task description
#
# Optional:
#   --model M            model name (default: MiniMax-M2.7)
#   --timeout S          wall-clock timeout in seconds (default: 600)
#   --read-only          Skip worktree + auto-commit; run in $REPO_ROOT.
#                        Meant for analysis/review tasks. Emits a WARNING
#                        if the secondary actually modified files. Safer
#                        than the default only if your task truly doesn't
#                        need to write (outside /tmp it'll touch primary).

set -euo pipefail
DELEGATE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DELEGATE_DIR/lib.sh"

job=""
task=""
model=""
timeout_s="600"
read_only=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --job)        job="${2:?}";       shift 2 ;;
        --task)       task="${2:?}";      shift 2 ;;
        --model)      model="${2:?}";     shift 2 ;;
        --timeout)    timeout_s="${2:?}"; shift 2 ;;
        --read-only)  read_only=1;        shift ;;
        -h|--help)    sed -n '1,20p' "$0"; exit 0 ;;
        *)            die "unknown arg: $1" ;;
    esac
done

[[ -n "$job"  ]] || die "--job is required"
[[ -n "$task" ]] || die "--task is required"
model="${model:-$DEFAULT_MODEL}"

load_env
require_env MINIMAX_API_KEY

mode="isolated"
if [[ "$read_only" == "1" ]]; then mode="read-only"; fi

if [[ "$read_only" == "1" ]]; then
    wt_path="$REPO_ROOT"
    info "mode: read-only — running in primary repo at $wt_path (no worktree, no auto-commit)"
else
    ensure_worktree "$job"
    wt_path="$(worktree_path "$job")"
fi

eval "$(export_env_for_shell "$job" "$model")"

info "delegating to $model in $wt_path (timeout ${timeout_s}s, mode=$mode)"
log_event "\"event\":\"start\",\"job\":\"$job\",\"model\":\"$model\",\"mode\":\"$mode\",\"timeout_s\":$timeout_s"

# Capture pre-run git state so read-only mode can report a true delta,
# not the count of pre-existing dirty files in primary.
pre_status=""
if [[ "$read_only" == "1" ]]; then
    pre_status="$(cd "$wt_path" && git status --porcelain 2>/dev/null || true)"
fi

# Autonomy preamble — MiniMax under `claude --print` has no
# interactive user; if the model asks for confirmation ("do you want me
# to proceed?") the run stalls and completes without the work done.
# Prepend a firm autonomy note so the model acts instead of asking.
autonomy_preamble='You are running non-interactively via claude --print. There is no human
to answer questions or grant permissions mid-task. Do NOT ask for
confirmation, ask clarifying questions, or offer to proceed — just
complete the task directly, writing files and running tools as needed.
When done, report briefly what you did.

---
Task:
'
full_task="${autonomy_preamble}${task}"

start_ts="$(date -u +%s)"
stdout_file="$(mktemp)"
cleanup() { rm -f "$stdout_file"; }
trap cleanup EXIT

set +e
# --dangerously-skip-permissions: secondary runs unattended under --print.
# Any permission prompt would hang (no tty to approve). The secondary is
# scoped to its own worktree (or to the primary repo if --read-only), so
# blast radius is bounded. Read the security notes in README.md.
( cd "$wt_path" && timeout "${timeout_s}s" claude --print --dangerously-skip-permissions "$full_task" ) >"$stdout_file" 2>&1
exit_code=$?
set -e

end_ts="$(date -u +%s)"
duration=$(( end_ts - start_ts ))

case "$exit_code" in
    0)   exit_reason="complete" ;;
    124) exit_reason="timeout"  ;;
    *)   exit_reason="error"    ;;
esac

# Post-run porcelain — used below for commit (isolated) or delta (read-only).
post_status="$(cd "$wt_path" && git status --porcelain 2>/dev/null || true)"

if [[ "$read_only" == "1" ]]; then
    # Delta = files the secondary actually touched during the run,
    # ignoring pre-existing dirty state in primary. No auto-commit.
    changed_count="$(
        { printf '%s\n' "$pre_status"; printf '%s\n' "$post_status"; } \
        | sort | uniq -u | grep -c . || true
    )"
    if [[ "$changed_count" -gt 0 ]]; then
        info "WARNING: --read-only was set but the secondary modified $changed_count file(s) in $wt_path"
        info "Review with: cd $wt_path && git status"
    fi
else
    # Isolated worktree: count porcelain entries (starts clean, so this IS the delta).
    changed_count=0
    if [[ -n "$post_status" ]]; then
        changed_count="$(printf '%s\n' "$post_status" | wc -l | tr -d ' ')"
    fi
    # Isolated worktree mode: auto-commit on the delegate branch so
    # `worktree.sh show|merge` have something to work with.
    if [[ -n "$post_status" ]]; then
        ( cd "$wt_path" && git add -A && \
          git -c user.name="delegate[$job]" -c user.email="delegate@foundry.local" \
              commit -q -m "delegate[$job]: ${task:0:60}" \
                     -m "Model: $model" -m "Exit: $exit_reason (${duration}s)" || true )
    fi
fi

log_event "\"event\":\"end\",\"job\":\"$job\",\"model\":\"$model\",\"mode\":\"$mode\",\"exit_reason\":\"$exit_reason\",\"duration_s\":$duration,\"files_changed\":${changed_count:-0}"

# Emit structured summary JSON to stdout (for primary to parse).
python3 - "$job" "$model" "$mode" "$exit_reason" "$exit_code" "$duration" "${changed_count:-0}" "$wt_path" "$stdout_file" <<'PY'
import json, sys, pathlib
job, model, mode, exit_reason, exit_code, duration, changed, wt_path, out_path = sys.argv[1:]
summary = pathlib.Path(out_path).read_text(errors="replace")
print(json.dumps({
    "job":           job,
    "model":         model,
    "mode":          mode,
    "exit_reason":   exit_reason,
    "exit_code":     int(exit_code),
    "duration_s":    int(duration),
    "files_changed": int(changed),
    "worktree":      wt_path,
    "summary":       summary,
}, indent=2))
PY
