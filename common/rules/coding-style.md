# Coding Style (Core)

## Change Philosophy

- Minimal diffs; avoid unrelated refactors
- Correctness → Clarity → Performance
- Don't optimize without measurement
- **KISS**, **YAGNI**, **DRY**

## Functions

- Small and single-purpose (<50 lines)
- If "and" in the name, it's doing too much
- Pure where possible; isolate side effects

## Data & State

- Prefer immutable data structures
- Avoid shared mutable state
- Strong types at boundaries

## Error Handling

- Fail fast with meaningful messages
- Handle at appropriate boundaries
- Log with context; don't swallow silently

## Naming & Comments

- Self-documenting names reduce comment need
- "What/why" comments OK; "how" comments are smell
- Document decisions for non-obvious tradeoffs

## Core Checklist

Before marking work complete:
- [ ] Minimal diff (no unrelated changes)
- [ ] Functions small and focused
- [ ] No deep nesting (>4 levels)
- [ ] Proper error handling
- [ ] No debug statements in production
- [ ] No hardcoded secrets

See project-specific styles in rule-library/style/.
