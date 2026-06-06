# Agent Orchestration

## Available Agents

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| architect-* | System design | Architectural decisions |
| tdd-guide-* | Test-driven dev | New features, bug fixes |
| code-reviewer-* | Code review | After writing code |
| security-reviewer-* | Security analysis | Before commits |
| build-error-resolver-* | Fix build errors | When build/lint/type check fails |
| e2e-test-* | Browser/GUI E2E | User flow testing |
| refactor-cleaner-* | Dead code cleanup | Code maintenance |
| doc-updater | Docs and codemaps | Run /update-codemaps |

Suffix: `-python`, `-typescript`, `-python-web`, `-python-qt`

## Plugin Agents

- **feature-dev** — 7-phase feature workflow
- **pr-review-toolkit** — PR analysis suite
- **code-review** — automated PR feedback
- **code-simplifier** — autonomous refactoring

## Immediate Usage (no prompt needed)

1. Complex feature → **plan mode**
2. Code written → **code-reviewer**
3. Bug fix / new feature → **tdd-guide**
4. Architecture decision → **architect**

## Parallel Execution

ALWAYS launch independent agents in parallel using multiple Task tool calls in one message.
