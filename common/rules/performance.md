# Performance Optimization

## Model Selection

- **Opus**: Planning, architecture, debugging, code review, judgment tasks
- **Sonnet**: Single-file edits, straightforward fixes, docs
- **Haiku**: Formatting, linting, mechanical transforms (only if agent specifies)

## Search Strategy

- **Grep/Glob**: Exact patterns, known symbols, specific files
- **Explore agent**: Open-ended, multi-round, uncertain scope
- **Sonnet/Haiku agents**: Mechanical search loops

Use Opus for judgment-based research. Prefer Explore over repeated Grep.

## Context Window

Avoid last 20% for: large refactors, multi-file features, complex debugging.
OK for: single-file edits, utilities, docs, simple fixes.

## Deep Reasoning

For complex tasks: `ultrathink` + **Plan Mode** + multiple critique rounds.
