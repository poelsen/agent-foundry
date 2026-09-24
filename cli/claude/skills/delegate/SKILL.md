---
name: delegate
description: Hand a task to another agent CLI (claude, codex, agy, copilot) as a managed job — own worktree, policy limits, audit log, review before merge. Use when asked to have another CLI do work.
---

# delegate — run a task on another agent CLI

Use this when the user wants another coding-agent CLI to do work: "have codex
fix this", "ask agy to review the branch", "run this on copilot in parallel".
Every run goes through one script, which enforces the
project's policy and records the job. For a one-shot question about text you
already have, the `codex-cli`, `agy-cli` and `copilot-cli` skills are lighter.

The runner (called `DELEGATE` below):

```bash
python3 .claude/skills/delegate/scripts/delegate.py <command> ...
```

## Before the first run

- `DELEGATE doctor` — installed CLIs, active policy, caveats.
- Run delegate commands **outside your own sandbox**: they start other CLIs
  that need network access and their own config directories, and background
  jobs must outlive the command. Claude Code: disable the sandbox for the
  call if sandboxing is on. Codex: request escalated permissions (the script
  refuses to run inside Codex's sandbox).

## Run a task

```bash
DELEGATE start --to codex --job fix-auth --task "<the user's task, verbatim>"
DELEGATE wait fix-auth        # exit 4 = still running: call wait again
```

- `start` returns at once. `wait` and `run` (start + wait in one call) wait
  at most 9 minutes; the job keeps running after that, so call `wait` again
  until the status is final. Give the shell call a timeout above 9 minutes
  (Claude Code: `timeout: 600000`), or pass `--wait <s>` / `--timeout <s>`
  below your shell tool's limit.
- `--to`: `claude`, `codex`, `agy` or `copilot`.
- **write** (default): a new worktree `../<repo>-delegate-<job>` on branch
  `delegate/<job>`, from `HEAD`. Your uncommitted changes are *not* in it
  unless you pass `--include-dirty`.
- `--mode read-only` for reviews and analysis: runs in your checkout (it sees
  uncommitted work) under the target's read-only settings; any file it
  changes anyway is reported in `warnings`.
- Optional: `--model`, `--effort`, `--timeout <s>` (the job's own limit),
  `--task-file <path|->` for long tasks, `--base <ref>`.
- Parallel work: `start` several jobs, then `wait` on each.

The target starts with an empty context. Pass the user's request verbatim,
plus what it needs: relevant paths, constraints, how to verify the result.

## Read the result

`wait`/`run` print JSON: `status` (`succeeded`, `failed`, `timeout`,
`cancelled`, `lost`), `summary` (the target's own final report),
`files_changed` and `commits` (this run's), `warnings`, `error`, and `next`
(commands to run next). Tell the user which CLI and model did the work, the status, the
summary and every warning. The summary is the delegate's claim, not proof:
review the diff before calling the work done.

## Review, merge, follow up

```bash
DELEGATE diff <job> [--patch]       # commits + changes; review them yourself
DELEGATE merge <job>                # only after the user approves
DELEGATE discard <job>              # only after the user approves
DELEGATE run --job <job> --resume --task "Also handle the empty case"
```

- `merge` merges `delegate/<job>` into your branch (`--no-ff`); for an
  `--include-dirty` job it applies only the delegate's delta, uncommitted.
- `discard` deletes the worktree and branch. It refuses (exit 6) while the job
  has unmerged commits, uncommitted changes in its worktree, or a worktree on
  another branch; `--force` overrides — only after the user agrees to lose it.
- A follow-up reuses the job's worktree; `--resume` continues the target's
  previous conversation.
- Also: `status <job>`, `list`, `log <job>` (raw output), `cancel <job>`.

## Targets

| `--to` | Runs | Read-only mode |
|--------|------|----------------|
| `claude` | Claude Code | edit tools removed; read-only shell allowed |
| `codex` | Codex CLI | Codex's read-only sandbox (refused if the policy bypasses it) |
| `agy` | Antigravity CLI | reads files; commands denied |
| `copilot` | Copilot CLI | reads files; no shell |

All limits live in `.delegate/policy.json` (commit it to share). Defaults: writes allowed, a
delegate may not delegate further (`max_depth` 1), 3 concurrent jobs, 30 min
timeout (max 2 h). See `scripts/README.md` for the policy format.

## Rules

1. Delegate only when the user asked for it or agreed to your suggestion — it
   spends another product's quota.
2. Confirm with the user before `merge` and `discard`.
3. Exit codes: 3 = refused by policy — report it, never work around it (for
   example by calling the other CLI directly); 4 = still running, call `wait`
   again; 6 = needs `--force`, which only the user can approve.
4. Never run `shell`: it is for a human in their own terminal.
5. Report honestly: which target and model ran, the final status, and whether
   you reviewed the diff. Never present a failed or unreviewed run as done.

Operators (humans): `DELEGATE shell --job <job> --to <cli>` opens that CLI
interactively in a job's worktree.
