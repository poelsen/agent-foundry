---
name: update-foundry
description: Update agent-foundry configuration to latest release
disable-model-invocation: true
allowed-tools: Bash(bash *)
---

# /update-foundry - Update agent-foundry Configuration

## Usage

- `/update-foundry` — check for a newer release and apply it
- `/update-foundry --check` — report only
- `/update-foundry --interactive` — full menu to add or change selections

## Instructions

Run the update script:

```bash
bash .claude/skills/update-foundry/scripts/update-foundry.sh $ARGUMENTS
```

Show the output to the user verbatim. After a successful update:
- Command and skill changes take effect immediately (or on the next session)
- Rule changes take effect next interaction
- Agent changes load on demand

If the script fails, help the user troubleshoot based on the error output.
