# Agent Orchestration

## Available Agents

| Agent | Purpose | Helps when |
|-------|---------|------------|
| code-reviewer-* | Code review | A substantial change is done and about to be committed or opened as a PR |
| security-reviewer-* | Security analysis | The change touches input handling, auth, endpoints, or sensitive data |
| e2e-test-* | Browser/GUI E2E | A user flow in a web or GUI app needs an end-to-end test |
| refactor-cleaner-* | Dead code cleanup | Asked to remove unused code, or a refactor left some behind |

Suffix: `-python`, `-typescript`, `-python-web`, `-python-qt`

## When to delegate

A subagent costs context handoffs both ways and its result comes back as a summary you can't check. Delegate when the work is independent and large, when a second read is wanted that isn't anchored on yours, or when the task is open-ended research across many files. Do small, well-understood changes yourself: a one-line fix needs no reviewer, and an obvious test needs no help.

Plan mode suits a feature that touches several modules or whose design is still open.

## Parallel Execution

When you do launch several independent agents, launch them in one message so they run concurrently.
