---
name: prj-resume
description: Resume work on a named project by loading its metadata and key files
---

# /prj-resume - Resume a Project

## Usage

- `/prj-resume <name>` — Load a project and resume work

## Instructions

1. Extract the project name from `$ARGUMENTS`. If empty, list available projects:
   ```bash
   ls -1 .claude/prjs/*.md 2>/dev/null | xargs -r -I{} basename {} .md
   ```
   Then stop and ask the user which project to resume.

2. Read `.claude/prjs/<name>.md` using the Read tool.
   - If the file doesn't exist, list available projects (as above) and stop.

3. Update the project status to active:
   ```bash
   sed -i 's/^status:.*$/status: active/' .claude/prjs/<name>.md
   ```

4. Present to the user:
   - **Project name and status** (from frontmatter)
   - **Goal** — what this project is about
   - **Current status** — what's done, what's pending
   - **Key decisions** — so settled points aren't re-litigated
   - **Next step** — from the Resume section
   - **Session restore** — print the `claude --resume` / `--fork-session --resume` commands from the Resume section

5. Ask the user how to proceed using AskUserQuestion with these options:
   - **Resume now** — keep current context, load project files on top (fastest, but current conversation stays in context)
   - **Compact and resume** — compact current conversation first, then load project files (frees context window, keeps summary of current work)
   - **Clear and resume** — clear conversation entirely, then load project files (cleanest switch, loses all current context)
   - **Restore full session** — use `claude --resume <id>` from terminal instead (restores original conversation history)

6. Based on the user's choice:
   - **Resume now**: Read each file in **Key Files** section (max 5 files, skip >500 lines or missing). Say "Ready to continue."
   - **Compact and resume**: Run `/compact`, then read Key Files as above. Say "Context compacted. Ready to continue."
   - **Clear and resume**: Run `/clear`, then re-read the prj file and Key Files. Say "Context cleared. Ready to continue."
   - **Restore full session**: Print the `claude --resume` command and tell the user to run it from their terminal.
