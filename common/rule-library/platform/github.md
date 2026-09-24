# GitHub Platform Rules

## Commit Linking

GitHub auto-closes issues from commit **body** keywords only:

```
feat: Add retry logic

Closes #42
```

- `Closes #N`, `Fixes #N`, `Resolves #N` in commit body → auto-closes issue on merge
- `(#N)` in subject line → creates link only, does NOT close

## Issues

- No GitHub Projects boards — issues live in the repo only
- Use `--json` with `gh issue view` / `gh pr view` (plain output errors on Projects classic)
