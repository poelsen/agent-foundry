#!/usr/bin/env bash
# .claude/skills/delegate/scripts/worktree.sh
#
# Worktree + result lifecycle for delegate jobs. Thin wrapper around
# `git worktree` with conventions for delegate branches.
#
# Usage:
#   worktree.sh create  JOB        # create or reuse worktree + branch
#   worktree.sh list                # list all delegate worktrees
#   worktree.sh show    JOB        # show commits + diffstat on the job branch
#   worktree.sh path    JOB        # print absolute path to the job's worktree
#   worktree.sh merge   JOB        # fast-forward or merge job branch into HEAD
#   worktree.sh discard JOB        # remove worktree + delete branch (destructive)

set -euo pipefail
DELEGATE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DELEGATE_DIR/lib.sh"

cmd="${1:-}"
job="${2:-}"

require_job() {
    [[ -n "$job" ]] || die "job required (usage: worktree.sh $cmd JOB)"
}

case "$cmd" in
    create)
        require_job
        ensure_worktree "$job"
        echo "$(worktree_path "$job")"
        ;;

    list)
        ( cd "$REPO_ROOT" && git worktree list ) | grep -E '(^|\s)delegate-|\[delegate/' || {
            info "no delegate worktrees"
            exit 0
        }
        ;;

    path)
        require_job
        echo "$(worktree_path "$job")"
        ;;

    show)
        require_job
        wt_path="$(worktree_path "$job")"
        [[ -d "$wt_path" ]] || die "no worktree for job '$job' at $wt_path"
        branch="$(worktree_branch "$job")"
        info "branch: $branch"
        info "path:   $wt_path"
        echo
        echo "── commits since master ─────────────────────────────"
        ( cd "$REPO_ROOT" && git log --oneline "master..$branch" 2>/dev/null ) || echo "(none)"
        echo
        echo "── diffstat vs master ───────────────────────────────"
        ( cd "$REPO_ROOT" && git diff --stat "master..$branch" 2>/dev/null ) || echo "(none)"
        ;;

    merge)
        require_job
        branch="$(worktree_branch "$job")"
        ( cd "$REPO_ROOT"
          current="$(git rev-parse --abbrev-ref HEAD)"
          info "merging $branch → $current"
          git merge --no-ff "$branch"
        )
        ;;

    discard)
        require_job
        wt_path="$(worktree_path "$job")"
        branch="$(worktree_branch "$job")"
        if [[ -d "$wt_path" ]]; then
            info "removing worktree: $wt_path"
            ( cd "$REPO_ROOT" && git worktree remove --force "$wt_path" )
        else
            info "no worktree to remove at $wt_path"
        fi
        if ( cd "$REPO_ROOT" && git show-ref --verify --quiet "refs/heads/$branch" ); then
            info "deleting branch: $branch"
            ( cd "$REPO_ROOT" && git branch -D "$branch" )
        fi
        ;;

    -h|--help|"")
        sed -n '1,14p' "$0"
        ;;

    *)
        die "unknown subcommand: $cmd (try: create|list|show|path|merge|discard)"
        ;;
esac
