---
name: private-remove
description: Remove a registered private config source
disable-model-invocation: true
allowed-tools: Bash(bash *)
---

# /private-remove - Remove Private Config Source

## Usage

- `/private-remove <prefix>` — Remove a private source by its prefix

## Instructions

Run the remove script, passing the prefix argument:

```bash
bash .claude/skills/private-remove/scripts/private-remove.sh $ARGUMENTS
```

Show the output to the user verbatim.
