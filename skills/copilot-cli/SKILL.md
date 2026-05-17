---
name: copilot-cli
description: Invocation contract for the local GitHub Copilot CLI — run a one-shot prompt on a non-Claude model (e.g. gpt-5.4) without spending Anthropic tokens. Used by review-process for cross-model review.
---

# copilot-cli — Local GitHub Copilot CLI

A thin reference skill. It does **one** thing: document the canonical,
non-interactive invocation of the locally installed GitHub Copilot CLI so
other skills (chiefly `review-process`) can route a prompt to a non-Claude
model without spending Anthropic tokens.

This replaced the retired VS Code Copilot MCP bridge. There is no MCP server,
no extension, and nothing to enable per workspace — if `copilot` runs in the
shell, this works.

## Prerequisite check (always do this first)

```bash
command -v copilot >/dev/null 2>&1 && copilot --version
```

- **Exit 0 + a version line** → the CLI is available; proceed.
- **Anything else** → the CLI is not installed/authenticated. Do **not** error
  out the caller. Report "copilot CLI unavailable" so the caller can fall back
  (review-process falls back to a second Claude run automatically).

First-time auth is interactive: the user runs `copilot` once and signs in.
The CLI is never installed or authenticated by this skill or by foundry setup.

## Canonical one-shot invocation

```bash
copilot -p "<prompt>" --model <model> --allow-all-tools -s --no-color
```

| Flag | Why it is required |
|------|--------------------|
| `-p, --prompt <text>` | Non-interactive mode; runs the prompt and exits. |
| `--model <model>` | Target model family, e.g. `gpt-5.4`. Omit to use the CLI default. |
| `--allow-all-tools` | Mandatory for non-interactive runs (else it blocks on a permission prompt). |
| `-s, --silent` | Emit only the model's response — no banner/spinner — so the output is capturable. |
| `--no-color` | Strip ANSI codes so captured text is clean. |

Run it with the `Bash` tool. The model's answer is the captured stdout. For
long tasks, use `Bash(run_in_background: true)` and collect the result when it
completes — `copilot -p` exits on its own when done.

Pass review context **in the prompt text** (paste the diff/snippet). Add
`--add-dir <path>` only when the model genuinely needs to read files itself;
prefer self-contained prompts for reproducibility.

## Models

Model IDs follow GitHub Copilot naming and depend on the user's subscription.
Common: `gpt-5.4`, `gpt-5.4-mini`, `claude-opus-4.6`, `claude-sonnet-4.6`,
`gemini-2.5-pro`, `grok-code-fast-1`. If a model is rejected, surface the CLI's
error verbatim rather than silently substituting another model.

## Cost & honesty

- Spends the user's **GitHub Copilot** subscription, not Anthropic tokens.
- Never claim a cross-model result if the CLI was unavailable or errored —
  say so and report which path was actually used.
