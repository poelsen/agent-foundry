# foundry-delegate

Tooling for running a secondary Claude Code CLI (or any Anthropic/OpenAI-compatible agent) in an isolated git worktree, pointed at a cheap model (MiniMax) **directly via MiniMax's native compatibility endpoint** — no local proxy process. Used by the primary Claude Code session to offload bulk work (scraping, analysis, review) without burning Max / Copilot quota.

## Two modes

- **Orchestrated** — primary Claude invokes `run.sh` via Bash; gets back a JSON summary. Fire-and-forget tasks.
- **Interactive** — operator sources `activate.sh` (or runs `launch.sh`) to enter a delegate shell and drive it by hand.

Both modes share the same worktree + env setup in `lib.sh`.

## One-time setup

```bash
# 1. Provide your MiniMax API key (standard or sk-cp Coding Plan key both work)
cp .claude/skills/delegate/scripts/.env.example .env
# edit .env — fill in MINIMAX_API_KEY
```

That's it. `.env` is gitignored. Never commit it.

The scripts point `ANTHROPIC_BASE_URL` at `https://api.minimax.io/anthropic` and `OPENAI_BASE_URL` at `https://api.minimax.io/v1`, so `claude`, `opencode`, `aider`, and plain `curl` all reach MiniMax with a single key.

## Orchestrated mode (primary → secondary)

From the primary Claude Code session (or any shell, inside the target project's git repo):

```bash
.claude/skills/delegate/scripts/run.sh \
  --job scrape \
  --timeout 600 \
  --task "Scrape product data from urls.txt, extract name/price/sku as JSON, save to data/products.json"
```

### Isolation modes

| Mode            | Worktree | Auto-commit | When to use |
|-----------------|----------|-------------|-------------|
| (default)       | yes      | yes         | Real work that may write files; primary keeps working safely. |
| `--read-only`   | no       | no          | Analysis/review/summary tasks. Runs in primary repo; warns loudly if the secondary writes anything. |

Output is a JSON object on stdout:

```json
{
  "job": "scrape",
  "model": "MiniMax-M2.7",
  "mode": "isolated",
  "exit_reason": "complete",
  "exit_code": 0,
  "duration_s": 143,
  "files_changed": 2,
  "worktree": "/home/you/git/claude-foundry-delegate-scrape",
  "summary": "..."
}
```

Secondary's file changes are auto-committed to the `delegate/<job>` branch in the sibling worktree. Primary can then:

```bash
.claude/skills/delegate/scripts/worktree.sh show    scrape    # inspect commits + diffstat
.claude/skills/delegate/scripts/worktree.sh merge   scrape    # merge into current branch
.claude/skills/delegate/scripts/worktree.sh discard scrape    # wipe worktree + branch
```

## Interactive mode (operator in a terminal)

### Option A — takeover launch

```bash
.claude/skills/delegate/scripts/launch.sh --job scrape --model MiniMax-M2.7
```

Preps everything and execs `claude` in the worktree. Your terminal *is* the secondary session. `/quit` or Ctrl+D returns to your primary shell.

### Option B — activate pattern (venv-style)

Open a fresh terminal, then:

```bash
source .claude/skills/delegate/scripts/activate.sh scrape MiniMax-M2.7
# now cwd is the worktree, env points at MiniMax
claude                    # drives MiniMax through Claude Code CLI
opencode run "task"       # or opencode, using OPENAI_BASE_URL
aider ...                 # or aider
curl ...                  # or plain curl/python scripts
```

When done, close the terminal — or unset the env vars and `cd` back.

## Layout & state

- Worktrees: `../<repo>-delegate-<job>/` (sibling to this repo — automatically isolated; never touches primary)
- Branches: `delegate/<job>` in this repo
- Event log: `.delegate/log.jsonl` (gitignored)

## Safety notes

- `.env` must never be committed.
- **`run.sh` uses `claude --dangerously-skip-permissions`** so the secondary can write files autonomously under `--print` (any prompt would hang the run). It also prepends a brief autonomy preamble to your task so the model doesn't stop mid-run to "ask for confirmation." Blast radius in the default mode is just the worktree; in `--read-only` it's your primary working tree — don't pass a task description the secondary would interpret as "rm -rf /".
- Secondary agents operate only within their worktree (default) — primary repo is untouched until `worktree.sh merge`.

## Adjacent: multimodal generation

MiniMax also hosts video / image / TTS / music / voice-cloning endpoints, all plain REST with the same key. They don't go through this tool — just direct HTTP. See `skills/minimax-multimodal/SKILL.md` (auto-activates when a task asks to generate media) for the endpoint table and a working async-polling pattern.

## Known gaps

- No async / job-id polling — `run.sh` is sync. Use Bash `run_in_background` if you need async.
- No cost metering — fine for flat-rate plans (MiniMax Coding Plan), not safe for metered providers. Add a cap arg if/when needed.
- MiniMax tool-use quality ≠ Claude. Expect occasional misfires. Scope tasks clearly.
- Multi-provider (Kimi, DeepSeek, etc.) routing is not supported in v1 — the scripts talk only to MiniMax. Add a proxy-based alternative (ccr, LiteLLM) if you need that later.
