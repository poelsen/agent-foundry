# /snapshot - Capture Session Context

**Model:** opus (requires judgment to identify important context)

Capture the current session state to a snapshot file for later resumption.

**Related commands:** `/snapshot-list` to view all snapshots, `/snapshot-restore` to resume from one.

## Process

Extract from session: active task, key decisions, files modified, open questions, next steps, user preferences.

Write to `.claude/snapshots/YYYY-MM-DD-HHMM-<short-desc>.md`:

```markdown
---
created: YYYY-MM-DDTHH:MM:SSZ
goal: "One-line objective"
status: in_progress | completed | blocked
---

## Active Task
[Current focus]

## Decisions Made
- [Decision and why]

## Files Modified
- path/file.py — what changed

## Open Questions
- [Unresolved items]

## Next Steps
- [ ] Next action
```

Guidelines: ~5KB max, summarize don't transcribe, use `file:line` refs not code snippets, max 5 decisions / 10 files / 5 questions. Keep 10 most recent, prune older.
