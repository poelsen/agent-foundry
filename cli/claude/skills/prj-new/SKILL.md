---
name: prj-new
description: Create a new named project for tracking work across sessions
---

# /prj-new - New Project

## Usage

- `/prj-new <name>` — Create a new named project

## Instructions

1. Run the script to create the project file:

```bash
bash .claude/skills/prj-new/scripts/prj-new.sh $ARGUMENTS
```

2. If the script reports the project already exists, inform the user and suggest `/prj-resume <name>` instead.

3. Read the new project file (path in script output).

4. Use the Edit tool to replace placeholder content (`<!-- Fill: ... -->`) in each section:
   - **Goal** — ask the user what this project is about if not clear from conversation
   - **Status** — "Just started" or summarize any existing work
   - **Decisions** — any decisions already made, or leave as "None yet"
   - **Key Files** — any relevant files already known

5. Confirm to the user that the project was created, and show the resume command.
