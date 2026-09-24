---
name: codex-cli
description: Invocation contract for the local OpenAI Codex CLI — one-shot, read-only prompts on OpenAI models from any coding agent. Used by review-process for cross-model review.
---

# codex-cli — Local OpenAI Codex CLI

A thin reference skill. It does **one** thing: document the canonical,
non-interactive invocation of the locally installed Codex CLI, so other skills
(chiefly `review-process`) can route a prompt to an OpenAI model directly —
no Copilot subscription needed.

## Prerequisite check (always do this first)

```bash
command -v codex >/dev/null 2>&1 && codex --version
```

- **Exit 0 + a version line** → the CLI is available; proceed.
- **Anything else** → not installed. Do **not** error out the caller. Report
  "codex CLI unavailable" so the caller can fall back.

First-time auth is interactive: the user runs `codex login` once. The CLI is
never installed or authenticated by this skill or by foundry setup.

## Canonical one-shot invocation

```bash
out=$(mktemp)
codex exec -m <model> -c 'model_reasoning_effort="medium"' \
  -s read-only --skip-git-repo-check --ephemeral \
  -o "$out" "<prompt>" </dev/null
cat "$out"
```

| Flag | Why it is required |
|------|--------------------|
| `exec` | Non-interactive mode; runs the prompt and exits. |
| `-m <model>` | Target model, e.g. `gpt-5.5`. Omit to use the CLI default. |
| `-c 'model_reasoning_effort="…"'` | `low` / `medium` / `high` / `xhigh`. Omit for the model default. |
| `-s read-only` | Reviewers read, never write. Codex's default for `exec`, stated explicitly. |
| `--skip-git-repo-check` | Allows running outside a git repository. |
| `--ephemeral` | Don't persist the session. |
| `-o <file>` | Writes only the final answer to the file; stdout also carries progress. |
| `</dev/null` | **Mandatory.** With stdin open, `codex exec` waits for more input. |

`--full-auto` no longer exists; do not pass it. Pass review context **in the
prompt text** (paste the diff/snippet); use `-C <dir>` only when the model
genuinely needs to read files itself.

Exit code 0 means success; 1 means a run, config or auth error (the reason is
on stderr).

## Models

List what the user's account can use with `codex debug models`. Common:
`gpt-5.5`, `gpt-5.6-sol`, `gpt-6-luna`. If a model is rejected, surface the
CLI's error verbatim rather than silently substituting another model.

## Cost & honesty

- Spends the user's **OpenAI / ChatGPT** plan, not the current agent's tokens.
- Never claim a cross-model result if the CLI was unavailable or errored —
  say so and report which path was actually used.
