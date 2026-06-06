# /snapshot-restore - Resume from Snapshot

**Model:** opus (requires judgment to present context)

Resume work from the most recent session snapshot.

## Process

1. Find the most recent `.md` file in `.claude/snapshots/` (sorted by filename, newest first)
2. Read its full contents
3. If the frontmatter contains a `trigger:` field, also read the referenced transcript for additional context
4. Present the snapshot contents to the user
5. Ask which threads/tasks from the snapshot they want to continue
