# GitHub Platform Rules

## Commit Linking

GitHub auto-closes issues from commit **body** keywords only:

```
feat: Add retry logic

Closes #42
```

- `Closes #N`, `Fixes #N`, `Resolves #N` in commit body → auto-closes issue on merge
- `(#N)` in subject line → creates link only, does NOT close

## GitHub Projects

- Use **new Projects experience** (not Classic)
- Every issue must be added to the project on creation
- Always use `--json` with `gh issue view` and `gh pr view` to avoid Classic Projects deprecation errors
