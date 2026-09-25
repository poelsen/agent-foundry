# Codemap System

## Reading Codemaps

Before modifying code in an unfamiliar module:
1. Read codemaps/INDEX.md for project overview
2. Read the specific module codemap for context

Do NOT read all codemaps upfront. Read only what you need.

## Updating Codemaps

Run /update-codemaps when:
- User requests it
- You've made structural changes (new modules, changed public APIs, new dependencies)

The command checks staleness automatically — only stale codemaps regenerate.

## AGENTS.md Pattern

The agent-foundry block in AGENTS.md already points to codemaps/INDEX.md —
don't repeat it. A project without that block should include:

```
## Architecture
Read codemaps/INDEX.md before making changes to unfamiliar modules.
Run /update-codemaps after significant structural changes.
```
