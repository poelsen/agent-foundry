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
        "matcher": "tool == \"Edit\" && tool_input.file_path matches \"\\\\.py$\"",
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

Each script has a comment header with the recommended matcher pattern.

## Context cost note

Type checker hooks (tsc-check, mypy-check) run after every edit and their output may consume Claude's context window. Enable these only when the type safety benefit outweighs the context cost for your project.

## Adding new hooks

Follow the existing pattern:
1. Read JSON from stdin (`input=$(cat)`)
2. Extract file path from `tool_input.file_path`
3. Run your tool, send output to stderr
4. Echo `$input` to stdout (pass-through)
