# Template: Scripts & CLI

## Simplicity

- Optimize for readability, not abstraction
- Inline is fine; don't over-engineer
- Comments for "why", not "what"

## Ergonomics

- Sensible defaults, explicit overrides
- Helpful --help output
- Exit codes: 0 success, non-zero failure
- Progress indicators for long operations

## Safety

- Dry-run mode for destructive operations
- Confirm before irreversible actions
- Validate inputs early

## Checklist

- [ ] Works with no arguments (or shows help)
- [ ] Clear error messages
- [ ] Non-zero exit on failure
- [ ] No hardcoded paths
