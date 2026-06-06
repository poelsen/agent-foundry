---
name: prj-pause
description: Save current session state to a named project for later resumption
---

# /prj-pause - Pause a Project

## Usage

- `/prj-pause <name>` — Save session state to a named project

## Instructions

1. Run the script to update the project file and get session info:

```bash
bash .claude/skills/prj-pause/scripts/prj-pause.sh $ARGUMENTS
```

2. Read the project file (path in script output).

3. Use the Edit tool to replace placeholder content (`<!-- Fill: ... -->`) in each section:
   - **Goal** — what this project is about (ask user if unclear from conversation)
   - **Status** — summarize what's done and what's in progress
   - **Decisions** — key decisions made during the session
   - **Key Files** — important files for this project
   - **Resume > Last action** — what was just done in this session
   - **Resume > Next step** — the precise next action to take (not vague)

   For existing projects where sections already have real content: update **Resume** (last action + next step) and optionally update **Status** and **Decisions** if they changed. Don't overwrite existing content with less detail.

4. Confirm to the user that the project state was saved, and show the resume command.
