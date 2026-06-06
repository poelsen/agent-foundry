# Git Workflow

## Branch Strategy

Feature Branch Workflow: short-lived branches, rebase only (no merge commits), squash before merge.

**Protected:** `master`, `release/*` — never push directly, require PR + review + CI pass.

## Branch Naming

```
feature/<initials>_<issue>_<desc>   bugfix/<initials>_<desc>
release/<major>_<minor>_<patch>     devel/<initials>_<desc>
```

Delete feature/bugfix branches after merge.

## Commit Format

```
[ISSUE-ID] <type>: <subject>

<body - wrap at 72 chars>

AI: Claude Opus 4.7
```

- Subject: 50 chars target, 70 max, imperative mood
- Types: feat, fix, refactor, docs, test, chore, perf, ci
- ISSUE-ID optional. See `github.md` for `Closes #N` linking.

## Pull Requests

1. Analyze full commit history with `git diff [base]...HEAD`
2. Draft comprehensive summary
3. Include test plan

## Release & Hotfix

Release: tag on master → hotfix needed: branch from tag → bugfix branch → fix → new tag → cherry-pick to master.
