---
name: snapshot-list
description: List all session snapshots with metadata
disable-model-invocation: true
allowed-tools: Bash(bash *)
---

# /snapshot-list - List Session Snapshots

## Usage

- `/snapshot-list` — Show all snapshots with date, goal, and status

## Instructions

Run the list script:

```bash
bash .claude/skills/snapshot-list/scripts/snapshot-list.sh $ARGUMENTS
```

Show the output to the user verbatim.
