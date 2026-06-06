---
name: delegate
description: Run a secondary Claude Code CLI on MiniMax models via this skill's scripts/. Offload bulk scraping/analysis/review to save Anthropic quota. Subcommands run, launch, status, merge, discard.
model: any
---

# Delegate — MiniMax Secondary Claude

Use this skill when the user wants to **offload work to a secondary Claude Code session running on MiniMax** instead of burning Anthropic / Copilot quota. The scripts live next to this SKILL.md in the `scripts/` subdir — at `.claude/skills/delegate/scripts/` in deployed projects. Read `.claude/skills/delegate/scripts/README.md` for full reference.

## Prerequisite

The user must have a MiniMax API key. The scripts read either `<repo>/.env` or `.claude/skills/delegate/scripts/.env` (copy `.env.example` from the same dir). If neither file has `MINIMAX_API_KEY=…`, stop and tell them to set it up first.

## Subcommand routing

Parse `$ARGUMENTS` as `<subcommand> [args...]`. If no subcommand, print the usage summary and stop.

### `run` — orchestrated fire-and-forget

Primary Claude invokes the delegate via Bash, gets back a JSON summary. Use for tasks the primary should not block on.

```bash
.claude/skills/delegate/scripts/run.sh \
  --job <NAME> \
  --task "<description>" \
  [--timeout <SECONDS>] \
  [--read-only]
```

- Default mode: secondary writes in an isolated sibling worktree on branch `delegate/<job>`. Auto-committed.
- `--read-only`: secondary runs in primary repo, no writes expected. Use for analysis/review/summary only.
- Returns JSON on stdout: `{job, model, exit_reason, exit_code, duration_s, files_changed, worktree, summary}`.

### `launch` — interactive takeover

Operator-only — Claude cannot execute this because it execs an interactive shell. Print the command for the user to run in their own terminal.

```bash
.claude/skills/delegate/scripts/launch.sh --job <NAME> [--model <MODEL>]
```

Default model: `MiniMax-M2.7`. Their terminal becomes the secondary session; `/quit` or Ctrl+D returns control.

### `status` — inspect delegate worktrees

```bash
.claude/skills/delegate/scripts/worktree.sh show [<JOB>]
```

Lists commits + diffstat for the job's worktree (or all worktrees if no job given).

### `merge` — pull delegate's work back

```bash
.claude/skills/delegate/scripts/worktree.sh merge <JOB>
```

Merges `delegate/<job>` branch into the current branch. Confirm with the user before running — this changes their working tree.

### `discard` — wipe delegate worktree

```bash
.claude/skills/delegate/scripts/worktree.sh discard <JOB>
```

Deletes the sibling worktree and the `delegate/<job>` branch. **Destructive** — confirm with user, and warn that any uncommitted work in the worktree will be lost.

## Usage summary (print when no subcommand)

```
/delegate <subcommand> [args]

  run       Fire orchestrated job on MiniMax (returns JSON when done)
            /delegate run --job scrape --task "scrape urls.txt to data.json"

  launch    Print command to start interactive MiniMax session
            /delegate launch --job scrape

  status    Show delegate worktree state
            /delegate status [job]

  merge     Merge delegate's work into current branch
            /delegate merge <job>

  discard   Wipe delegate worktree and branch (destructive)
            /delegate discard <job>

Setup: copy .claude/skills/delegate/scripts/.env.example to <repo>/.env
       (or .claude/skills/delegate/scripts/.env) and add MINIMAX_API_KEY.
Full docs: .claude/skills/delegate/scripts/README.md
```

## Rules

1. **Confirm before destructive actions** — `merge` and `discard` modify state outside the delegate's sandbox.
2. **Never invoke `launch` directly** — it execs `claude` interactively; print the command for the operator instead.
3. **Check `.env` exists before running anything** — fail fast with a clear setup message if not.
4. **Pass user task descriptions verbatim** to `--task` — don't paraphrase or summarize them.
