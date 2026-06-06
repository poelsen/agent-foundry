---
name: learn
description: Capture cross-project technical patterns. TRIGGER: just solved a non-obvious bug whose root cause would generalize (library quirk, framework gotcha, workaround). SKIP: trivial fixes, user preferences.
---

# /learn - Extract Reusable Patterns

**Model:** opus (requires judgment)

## When to Invoke

The frontmatter `description` gates invocation; this section guides extraction quality once the skill fires.

Grounded examples from this repo:
- Qt signal-triggered widget deletion → use-after-free (`qt-defer-widget-rebuild.md`)
- `tar --force-local` for Windows drive-letter paths (commit `41fc268`)

Where rejected content should go instead:
- Codebase-specific conventions → `CLAUDE.md` or codemaps
- User preferences, project state, team conventions → auto-memory

Rule of thumb: if a developer at a different company on a different project could hit the same issue, it's a `/learn` candidate.

## 5-Step Process

### Step 1: Identify

Review the session for the most valuable pattern. Ask yourself:
- What problem was solved?
- What was non-obvious about the solution?
- Would this help in a future session?

If nothing qualifies, tell the user: "No non-trivial patterns identified in this session."

### Step 2: Generalize

Extract the reusable principle — not the specific code. The pattern should:
- Apply beyond this exact scenario
- Be concise enough to scan in 30 seconds
- Include trigger conditions (when to apply it)

### Step 3: Draft

Write the skill file using this exact template:

```markdown
# [Pattern Name]

**Extracted:** [Date]
**Context:** [When this applies]

## Problem
[What this solves — one paragraph]

## Solution
[The pattern/technique — keep concise]

## Example
[Code or steps if applicable]

## When to Use
[Trigger conditions — bullet list]
```

### Step 4: Validate

Before saving, check:
- [ ] Is this genuinely reusable? (Would another developer benefit?)
- [ ] Is it general enough? (Not tied to one specific codebase)
- [ ] Is the Problem section clear? (Someone unfamiliar could understand)
- [ ] Is the Solution actionable? (Not just "be careful")

If any check fails, revise the draft.

### Step 5: Save

1. Ask the user for a **category** (e.g., `python`, `git`, `debugging`, `pyside6`)
2. Ask for a **save location**:
   - **claude-foundry repo** (default): `<config_repo>/skills/learned/<category>/<name>.md` — shared across machines
   - **project-local**: `.claude/skills/learned-local/<category>/<name>.md` — stays in this project
3. Show the user the exact file path and full content
4. Get explicit confirmation before writing
5. Create directories if needed
6. After saving: remind to commit/push if saved to claude-foundry repo, and run `setup.py init` to deploy
