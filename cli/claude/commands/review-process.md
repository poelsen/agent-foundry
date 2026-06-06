# /review-process - Tiered Review Orchestration

Apply the review-process skill to the user's request: $ARGUMENTS

Steps:

1. Read `.claude/skills/review-process/SKILL.md` for the canonical process
   (risk tiers, modes, routing, finding ledger, completion criteria).
2. Use the **Process Selection** table in `SKILL.md` to determine which
   sub-files apply to the artifact under review.
3. Read every applicable sub-file with the Read tool — they are not
   auto-loaded:
   - `.claude/skills/review-process/general.md`
   - `.claude/skills/review-process/software.md`
   - `.claude/skills/review-process/python.md`
   - `.claude/skills/review-process/python-non-gui.md`
   - `.claude/skills/review-process/python-gui.md`
   Always include `general.md` plus every more-specific file whose trigger
   applies. They are additive, not exclusive.
4. Determine risk tier and review mode from the triggers.
5. **Detect the runtime** (Claude Code vs Copilot CLI vs unknown, and whether
   Copilot MCP is wired in) using the bash snippet in **Model strategy →
   Runtime detection** in `SKILL.md`. The detected profile shapes which model
   strategies are actually runnable.
6. **For every tier**, unless the user already specified a model strategy or
   exact models in their invocation, call `AskUserQuestion` to confirm the
   strategy before producing the review header. Use the tier-recommended
   default as the first option. See **Model strategy → When to ask the user
   for a strategy** in `SKILL.md`.
7. Produce the review header (record host profile, MCP availability, chosen
   strategy, requested vs actual models) and run the review.
