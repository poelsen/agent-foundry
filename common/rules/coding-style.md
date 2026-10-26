# Coding Style (Core)

## Change Philosophy

- Minimal diffs; avoid unrelated refactors
- Correctness → Clarity → Performance
- Don't optimize without measurement
- **KISS**, **YAGNI**, **DRY**
- No debug leftovers (prints, commented-out code)

## Functions

- Small and single-purpose (<50 lines), nesting no deeper than 4 levels
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
