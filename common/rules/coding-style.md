# Coding Style (Core)

## Change Philosophy

- Minimal diffs; avoid unrelated refactors
- Correctness → Clarity → Performance
- Don't optimize without measurement
- **KISS**, **YAGNI**, **DRY**
- No debug leftovers (prints, commented-out code)

## Working Method

- Reproduce a bug before fixing it
- Read the code you're changing, and its callers, before editing
- Smallest change that fixes the cause, not the symptom
- Verify by running it, and say what you ran
- State a routine assumption and continue; ask when different readings lead to materially different work

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
