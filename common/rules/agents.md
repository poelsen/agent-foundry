# Agent Orchestration

## Available Agents

| Agent | Purpose | Helps when |
|-------|---------|------------|
| architect-* | System design | A change spans modules or sets a pattern others will follow |
| tdd-guide-* | Test-first development | The project works test-first, or a behaviour needs pinning down before coding |
| code-reviewer-* | Code review | A substantial change is done and about to be committed or opened as a PR |
| security-reviewer-* | Security analysis | The change touches input handling, auth, endpoints, or sensitive data |
| build-error-resolver-* | Fix build errors | Build, lint or type check fails and the cause isn't obvious |
| e2e-test-* | Browser/GUI E2E | A user flow in a web or GUI app needs an end-to-end test |
| refactor-cleaner-* | Dead code cleanup | Asked to remove unused code, or a refactor left some behind |
| doc-updater | Docs and codemaps | Codemaps or docs are stale after a structural change |

Suffix: `-python`, `-typescript`, `-python-web`, `-python-qt`

## Plugin Agents

- **feature-dev** — 7-phase feature workflow
- **pr-review-toolkit** — PR analysis suite
- **code-review** — automated PR feedback
- **code-simplifier** — autonomous refactoring

## When to delegate

A subagent costs context handoffs both ways and its result comes back as a summary you can't check. Delegate when the work is independent and large, when a second read is wanted that isn't anchored on yours, or when the task is open-ended research across many files. Do small, well-understood changes yourself: a one-line fix needs no reviewer, and a function with an obvious test needs no tdd-guide.

Plan mode suits a feature that touches several modules or whose design is still open.

## Parallel Execution

When you do launch several independent agents, launch them in one message so they run concurrently.
