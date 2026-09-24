# delegate.py — managed cross-CLI delegation

`delegate.py` lets one coding-agent CLI hand a task to another — Claude Code →
Codex, Codex → Antigravity, Copilot → Claude Code, any direction —
as a managed job. It is stdlib-only Python (3.9+, POSIX) and deploys with the
`delegate` skill to `.claude/skills/delegate/` (Claude Code) and
`.agents/skills/delegate/` (Copilot CLI, Codex, Antigravity).

## What "managed" means

| Control | How |
|---------|-----|
| Isolation | Write jobs run in their own worktree `../<repo>-delegate-<job>` on branch `delegate/<job>`. Read-only jobs run in place under the target's read-only settings. |
| Review gate | Nothing reaches your branch until `merge`. Leftover uncommitted work is auto-committed (unsigned, hooks skipped) on the job branch as `delegate (<target>)`; common build artifacts (`__pycache__`, `*.pyc`, `node_modules`, …) are left out. `discard` refuses to drop unmerged commits, uncommitted worktree changes or a worktree moved to another branch without `--force`. |
| Policy | `.delegate/policy.json`: allowed targets, write access, depth, concurrency, timeouts, per-target defaults, extra environment. Validated strictly — an unknown key or wrong type is an error, never ignored. Flags can only tighten it. |
| Loop guard | Each child gets `FOUNDRY_DELEGATE_DEPTH`/`_CHAIN`/`_TARGET`/`_JOB`, and a caller inside a running job's worktree counts as that job's depth even if its CLI filtered the environment. At `max_depth` (default 1) a delegate is refused, and its prompt tells it not to delegate. |
| Credentials | Variables that identify the calling session are stripped, including credentials like Claude Code's messaging token and Antigravity's CSRF token. Each child keeps only its own CLI's credentials (`ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN` for claude, `OPENAI_API_KEY` for codex, `GEMINI_API_KEY` for agy, `COPILOT_GITHUB_TOKEN` for copilot), plus anything in the policy's `pass_env`. |
| Supervision | Every run has a detached supervisor: the target runs in its own process group; on timeout or `cancel` the group gets SIGTERM, then SIGKILL after 10 s; processes it leaves behind are swept when it exits; on Linux the target dies with its supervisor. A run is `lost` only when its supervisor process is gone, and whatever it left is stopped then. |
| Tamper checks | Refs are snapshotted before and after each run; any branch or tag that moved (other than job branches) is reported. A write job whose worktree ends up on another branch is flagged and not auto-committed. Files that change during a read-only run are listed. |
| Audit | State lives in the git common dir, shared by every worktree (bare repositories included) and invisible to project tools: `.git/delegate/jobs/<job>/<run>/` (prompt, raw stdout/stderr, summary) and one line per event in `.git/delegate/log.jsonl`. |

These are guardrails for cooperating agents, not a security boundary: a
delegate with an unrestricted shell could still start another CLI by hand.

## Commands

```
delegate.py run|start --to <cli> --task TEXT | --task-file PATH|-
                      [--job NAME] [--mode write|read-only] [--model M] [--effort E]
                      [--timeout S] [--include-dirty] [--base REF] [--resume]
delegate.py wait <job> [--timeout 540]      status <job> [--run N]
delegate.py list [--json]                   log <job> [--run N] [--lines 60]
delegate.py cancel <job>                    diff <job> [--patch]
delegate.py merge <job>                     discard <job> [--force]
delegate.py doctor
delegate.py shell --job NAME [--to CLI]     # operator only (needs a terminal)
```

`run` is `start` plus `wait --timeout <--wait>`: when the wait ends first,
the job keeps running and `wait` picks it up later.

Exit codes: 0 succeeded, 1 failed (or timeout/cancelled/lost), 2 usage error,
3 refused by policy, 4 still running, 5 target unavailable, 6 needs `--force`
(ask the user).

`run`, `wait` and `status` print one JSON object:

```json
{
  "job": "fix-auth", "run": 1, "status": "succeeded",
  "target": "codex", "mode": "write", "model": "gpt-5.5",
  "host": "claude", "chain": "claude>codex",
  "workdir": "/home/you/git/app-delegate-fix-auth", "branch": "delegate/fix-auth",
  "exit_code": 0, "duration_s": 212.4,
  "files_changed": ["src/auth.py", "tests/test_auth.py"], "commits": 1,
  "session_id": "0199…", "usage": {"input_tokens": 51234, "output_tokens": 2311},
  "error": null, "warnings": [],
  "summary": "Fixed the token refresh race … ran pytest: 48 passed.",
  "summary_file": ".../.git/delegate/jobs/fix-auth/1/summary.md",
  "output_dir": ".../.git/delegate/jobs/fix-auth/1",
  "next": ["python3 … diff fix-auth", "python3 … merge fix-auth   # after the user approves", "…"]
}
```

`files_changed` and `commits` cover this run only (a follow-up reports its
own); `diff` shows everything a merge would bring. `base_note` appears when
your checkout had uncommitted changes the delegate could not see;
`summary_truncated` when the summary exceeded 20,000 characters (the full text
is in `summary_file`).

## How each target is run

| Target | Write mode | Read-only mode | Result from |
|--------|------------|----------------|-------------|
| `claude` | `claude -p --output-format json --dangerously-skip-permissions --disallowedTools "Bash(git push:*)"` | `--permission-mode dontAsk --disallowedTools Edit,Write,NotebookEdit,…` | JSON `result`, `session_id`, cost |
| `codex` | `codex exec --json -o <file> -c sandbox_mode="workspace-write"` | `-c sandbox_mode="read-only"` | `-o` file; `thread_id` and usage from events |
| `agy` | `agy -p … --output-format json --add-dir <workdir> --dangerously-skip-permissions` | no auto-approval: file reads work, commands are denied | JSON `response`, `conversation_id`, usage |
| `copilot` | `copilot -p … --output-format json --allow-all-tools --deny-tool "shell(git push)" --no-ask-user` | `--deny-tool write --deny-tool shell` | last `assistant.message`; `result` event |

All four take `--model`, `--effort` and resume (`claude --resume`,
`codex exec resume`, `agy --conversation`, `copilot --resume=`). Prompts go
over stdin to Claude Code and Codex. Antigravity and Copilot take the prompt
as an argument, capped at 128 KiB on Linux, so a longer task is passed as a
pointer to its prompt file. Antigravity works in a scratch directory unless
the workspace is added, hence `--add-dir`.

Caveats found while building this (CLI versions: Claude Code 2.1, Codex
0.156, Antigravity 1.2.10, Copilot CLI 1.0.69):

- **Codex's sandbox** needs unprivileged user namespaces (bubblewrap). Where
  it can't start, Codex can't run any command, not even to read a file.
  `doctor` checks this. The fix is `"targets": {"codex": {"sandbox": "bypass"}}`,
  which runs Codex without its sandbox and leaves the worktree as the only
  fence — so read-only Codex jobs, which run in your checkout, are refused
  under it. `"network": true` lets sandboxed write jobs reach the network, for
  example to install dependencies.
- **Antigravity's `--sandbox`** isn't used: with auto-approval, agy simply
  bypasses a sandbox that fails to start. Read-only agy therefore has no
  shell. A headless agy whose only tool call is denied exits 0 with an empty
  response; that is reported as `failed`, with agy's explanation.
- **Copilot's deny rules beat allow rules**, so read-only Copilot can't be
  given an allowlist of read-only shell commands; it gets file tools only.
- **Claude Code's `plan` mode** also blocks writes, but it frames every answer
  as a plan, so read-only uses `dontAsk` with the edit tools removed.

## Policy — `.delegate/policy.json`

Optional; the defaults apply without it. It is read from the main checkout,
so a delegate can't loosen it by editing its worktree's copy. Commit it to
share it with the team, and review changes to it like code. Unknown keys and
wrong types are errors.

```json
{
  "allow_write": true,
  "max_depth": 1,
  "max_concurrent": 3,
  "default_timeout_s": 1800,
  "max_timeout_s": 7200,
  "worktree_root": null,
  "pass_env": [],
  "targets": {
    "claude":  {"enabled": true, "model": null, "effort": null},
    "codex":   {"enabled": true, "model": "gpt-5.5", "effort": "high",
                "sandbox": "enforce", "network": false},
    "agy":     {"enabled": true, "model": "gemini-3.1-pro-high"},
    "copilot": {"enabled": false}
  }
}
```

- `max_depth`: how many delegation hops are allowed. At 1, only the top-level
  session delegates. At 2, a delegate may delegate once more (claude → codex
  → agy), and so on.
- `worktree_root`: where job worktrees go (default: the repo's parent dir; a
  relative path is relative to the main checkout). Keep them outside the
  repo, or test runners and linters walking the repo will pick up a second
  copy of the code.
- `pass_env`: extra variable names every child keeps — for example another
  provider's key that the project's own tests need.
## Known gaps

- POSIX only (uses process groups and `fcntl`); no Windows support. Outside
  Linux, a target doesn't die with a killed supervisor; it is stopped when
  the run is next found `lost`.
- Processes that start their own session (daemons) escape the process-group
  sweep.
- Read-only change detection doesn't see ignored files.
- No cost cap across runs. Claude Code reports per-run cost; the other
  targets report token counts.
- An agent can only be *asked* not to push; only Claude Code and Copilot get a
  deny rule for `git push`. A push shows up afterwards as a moved
  `refs/remotes/...` ref in `warnings`.
