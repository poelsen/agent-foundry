---
name: agy-cli
description: Invocation contract for the local Google Antigravity CLI (agy) — one-shot prompts on Gemini models from any coding agent. Used by review-process for cross-model review.
---

# agy-cli — Local Google Antigravity CLI

A thin reference skill. It does **one** thing: document the canonical,
non-interactive invocation of the locally installed Antigravity CLI (`agy`),
so other skills (chiefly `review-process`) can route a prompt to a Gemini
model.

For work that edits files or runs for a while (implement, fix, refactor), use
the `delegate` skill instead (`--to agy`): it gives Antigravity its own
worktree, applies the project's delegation policy, and records the job.

## Prerequisite check (always do this first)

```bash
command -v agy >/dev/null 2>&1 && agy --version
```

- **Exit 0 + a version line** → the CLI is available; proceed.
- **Anything else** → not installed. Do **not** error out the caller. Report
  "agy CLI unavailable" so the caller can fall back.

`agy` must be signed in (run `agy` once interactively), or configured for a
Gemini API key (`GEMINI_API_KEY` with `modelProvider: "gemini"` in its
settings). Unauthenticated, even read-only commands wait for an OAuth browser
sign-in — so always run with a timeout.

## Canonical one-shot invocation

```bash
timeout 600 agy -p "<prompt>" --model <model> --output-format json </dev/null \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); r=(d.get("response") or "").strip()
ok=d.get("status")=="SUCCESS" and r; print(r if ok else d.get("error") or "no answer"); sys.exit(0 if ok else 1)'
```

| Flag | Why it is required |
|------|--------------------|
| `-p "<prompt>"` | Non-interactive (print) mode; runs one turn and exits. |
| `--model <model>` | Target model slug, e.g. `gemini-3.1-pro-high`. An unknown slug fails hard. |
| `--output-format json` | One JSON object: `response`, `status`, `error`, `usage`. |
| `</dev/null` | Keeps it from reading stdin. |
| `timeout` | Guards against a sign-in prompt hanging the caller. |

`-p` takes the prompt as a single command-line argument, which Linux caps at
128 KiB. For larger material (a big diff), write it to a file under a
directory passed with `--add-dir <dir>` and reference the file's path in a
short prompt instead.

Without `--dangerously-skip-permissions`, tools that need approval are
soft-denied — which is what a read-only reviewer wants. A denial can leave the
model with **no answer at all** while `status` is still `SUCCESS`: `response`
is empty, `denied_actions` lists the tool, and stderr says "no output
produced". The example above exits 1 in that case: treat it as a failed run,
never as a clean review, and re-run with a prompt that says to answer in text
without running commands.

Pass review context **in the prompt text**; add `--add-dir <path>` only when
the model genuinely needs to read files itself.

Exit codes: 0 success, 1 run error, 2 bad command line, 3 model/API failure
(with an `AGY_ERROR: {...}` line on stderr — transient 503s happen; one retry
is reasonable).

## Models

List them with `agy models`. Common: `gemini-3.1-pro-high`,
`gemini-3.8-flash-medium`. If a model is rejected, surface the CLI's error
verbatim rather than silently substituting another model.

## Cost & honesty

- Spends the user's **Google Antigravity** quota, not the current agent's tokens.
- Never claim a cross-model result if the CLI was unavailable or errored —
  say so and report which path was actually used.
