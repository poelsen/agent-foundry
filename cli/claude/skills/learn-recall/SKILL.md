---
name: learn-recall
description: Search and list learned skill patterns
disable-model-invocation: true
allowed-tools: Bash(bash *)
---

# /learn-recall - Search Learned Skills

## Usage

- `/learn-recall` — List all learned skills grouped by category
- `/learn-recall <keyword>` — Search skills by keyword

## Instructions

Run the search script, passing through user arguments:

```bash
bash .claude/skills/learn-recall/scripts/learn-recall.sh $ARGUMENTS
```

Show the output to the user verbatim.
