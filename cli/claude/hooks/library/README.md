# Hook Library

Reusable hook scripts for per-project use. These are **not active globally** — projects reference them in their `.claude/settings.json` to opt in.

## Why a library?

Formatters and type checkers are language/project-specific. Rather than polluting the global hooks config, this library provides ready-made scripts that projects can activate when needed.

## Available hooks

| Script | Type | Trigger | What it does |
|--------|------|---------|--------------|
| `prettier-format.sh` | PostToolUse | Edit `.ts/.tsx/.js/.jsx` | Runs `prettier --write` on edited file |
| `ruff-format.sh` | PostToolUse | Edit `.py` | Runs `ruff format` on edited file |
| `tsc-check.sh` | PostToolUse | Edit `.ts/.tsx` | Runs `tsc --noEmit`, shows errors in edited file |
| `mypy-check.sh` | PostToolUse | Edit `.py` | Runs `mypy` on edited file |
| `cargo-check.sh` | PostToolUse | Edit `.rs` | Runs `cargo check`, shows errors |

## How to use

Add a hook entry to your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|MultiEdit|Write",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/library/ruff-format.sh"
          }
        ],
        "description": "Auto-format Python files with ruff"
      }
    ]
  }
}
```

Claude Code matches hooks on the tool name only, so every script is
registered for `Edit|MultiEdit|Write` and filters the edited file's
extension itself (e.g. `ruff-format.sh` ignores anything but `*.py`).

The same scripts run as Codex hooks (`.codex/hooks.json`, matcher
`apply_patch|Edit|Write`) and Antigravity hooks (`.agents/hooks.json`, matcher
`write_to_file|replace_file_content|multi_replace_file_content`). They source `_edited-files.sh`, which lists the
edited files from any of the three hook inputs — Claude's
`tool_input.file_path`, the paths in Codex's `apply_patch` patch, or
Antigravity's `toolCall.args.TargetFile` — and they print nothing on
stdout, because Codex treats non-hook JSON there as a failed hook run.

## Context cost note

Type checker hooks (tsc-check, mypy-check) run after every edit and their output may consume Claude's context window. Enable these only when the type safety benefit outweighs the context cost for your project.

## Adding new hooks

Follow the existing pattern:
1. Read JSON from stdin (`input=$(cat)`)
2. Extract file path from `tool_input.file_path`
3. Run your tool, send output to stderr
4. Echo `$input` to stdout (pass-through)
