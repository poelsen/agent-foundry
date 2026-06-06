# Hooks System

## Hook Types

- **PreToolUse**: Before tool execution (validation, blocking)
- **PostToolUse**: After tool execution (validation, logging)
- **PreCompact**: Before context compaction
- **SessionEnd**: On session termination

## Per-Language Hooks

Foundry ships per-language formatter and type-checker hooks as shell scripts in `hooks/library/`. These are selected during `setup.py init` based on the project's detected languages and written into the project's `.claude/settings.json` PostToolUse hooks.

Available scripts:
- `ruff-format.sh` — Python formatting
- `mypy-check.sh` — Python type checking
- `prettier-format.sh` — JS/TS formatting
- `tsc-check.sh` — TypeScript type checking
- `cargo-check.sh` — Rust type checking

## Workflow Hooks — Not Shipped

Foundry does **not** ship workflow-style hooks (dev server blockers, tmux reminders, git push pauses, doc blockers, PR-URL loggers, auto-snapshotters, etc.). A batch of 7 such hooks was reviewed with `megamind-adversarial` and every one of them was either broken, redundant with Claude Code's built-in rules, or too opinionated/personal-workflow to be useful defaults across foundry's user base. The hooks were deleted along with issue #3 (which had proposed adding a selection menu for them).

If you want workflow automation specific to your own setup, add it directly to your project's `.claude/settings.json` — Claude Code's hook machinery is well-documented and those hooks belong at the user/project level, not in foundry's shipping defaults.
