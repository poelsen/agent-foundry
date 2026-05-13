# claude-foundry

<!-- claude-foundry -->
## Rules

Read rules in `.claude/rules/` before making changes:
- `enterprise.md` — Enterprise security (production, compliance)
- `github.md` — GitHub workflow (gh CLI, PR conventions)
- `python.md` — Python tooling (uv, pytest, ruff)
- `scripts.md` — Scripts & CLI (argument parsing, error handling)
- `agents.md` — Agent orchestration
- `architecture.md` — Architecture principles
- `codemaps.md` — Codemap system
- `coding-style.md` — Code style guidelines
- `git-workflow.md` — Git workflow and commit conventions
- `hooks.md` — Hooks system
- `performance.md` — Performance and model selection
- `security.md` — Security checks and practices
- `testing.md` — Testing requirements (TDD, 80% coverage)

## Foundry Defaults

```bash
uv sync --extra dev  # Setup
uv run pytest  # Tests
```

## Architecture

Read `codemaps/INDEX.md` before modifying unfamiliar modules.
Run `/update-codemaps` after significant structural changes.

## Documentation

Read `docs/` for detailed project documentation (if it exists).
- `docs/ARCHITECTURE.md` — design decisions and patterns
- `docs/DEVELOPMENT.md` — setup and workflow guides
<!-- /claude-foundry -->

