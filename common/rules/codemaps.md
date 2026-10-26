# Codemap System

## Reading Codemaps

This applies to projects that have a `codemaps/` directory. Don't create one unasked.

Before modifying code in an unfamiliar module:
1. Read codemaps/INDEX.md for project overview
2. Read the specific module codemap for context

Don't read all codemaps upfront. Read only what you need.

## Updating Codemaps

Run /update-codemaps when:
- User requests it
- You've made structural changes (new modules, changed public APIs, new dependencies)

The command checks staleness automatically — only stale codemaps regenerate.
