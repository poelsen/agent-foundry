"""Claude Code adapter — deploys into <project>/.claude/; its instructions
come from the shared AGENTS.md.

This is the full-fidelity target: it consumes every artifact type. Claude
Code reads AGENTS.md only while no CLAUDE.md exists, and loads .claude/rules/
alongside it — so the portable rules live in AGENTS.md alone, .claude/rules/
keeps the Claude-only ones, and a project's CLAUDE.md is moved into AGENTS.md
(see shared.write_agents_md).
"""

from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess
from pathlib import Path

from ..console import confirm
from ..deploy import (
    copy_agents,
    copy_commands,
    copy_hooks,
    copy_learned_skills,
    copy_rules,
    copy_skills,
    generate_settings_json,
)
from ..instructions import has_agent_foundry_header
from ..private import (
    clean_private_files,
    deploy_private_source,
    discover_private_content,
    redeploy_private_sources,
    validate_prefix,
)
from ..registry import CLAUDE_ONLY_RULES
from .base import AGENTS_MD, MCP_JSON, CliAdapter, DeployContext, DeployResult, Selections, Skipped

# First Claude Code release that reads AGENTS.md.
AGENTS_MD_SINCE = (2, 1, 277)


@functools.cache
def _installed_claude_version() -> tuple[int, ...] | None:
    """Version of the `claude` on PATH, or None if absent or unparsable."""
    exe = shutil.which("claude")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(g) for g in m.groups()) if m else None


def _may_move_claude_md(project: Path, ctx: DeployContext) -> bool:
    """Whether CLAUDE.md may be moved into AGENTS.md (shared.write_agents_md
    does the move). One the foundry wrote — it carries the marker — or an
    empty one moves without asking; for any other, ask first."""
    claude_md = project / "CLAUDE.md"
    if not claude_md.is_file():
        return True
    try:
        content = claude_md.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print("\n  CLAUDE.md isn't UTF-8 text — skipping project (re-save it as UTF-8)")
        return False
    if has_agent_foundry_header(content) or not content.strip():
        return True
    why = ("Claude Code reads AGENTS.md only while no CLAUDE.md exists, so setup moves "
           "CLAUDE.md's content into AGENTS.md and deletes CLAUDE.md.")
    if ctx.interactive:
        print(f"\n  CLAUDE.md exists ({content.count(chr(10))} lines, {len(content)} chars) "
              "without the agent-foundry marker.")
        print(f"  {why}")
        print("    [M] Move — CLAUDE.md's content goes into AGENTS.md, above the foundry block")
        print("    [Q] Quit — Abort setup entirely")
        if input("  Choice [M/Q]: ").strip().upper() == "Q":
            print("\n  Aborted. No changes made to CLAUDE.md.")
            return False
        return True
    if ctx.force:
        print("\n  WARNING: CLAUDE.md exists without agent-foundry marker.")
        print(f"  {why}")
        if confirm("  Proceed with the move?", default=False):
            return True
        print("  Aborted.")
        return False
    print("\n  CLAUDE.md exists without agent-foundry marker — skipping project")
    print(f"  {why}")
    print("")
    print("  To move it, run setup.py init interactively:")
    print(f"    python3 <agent-foundry>/tools/setup.py init {project}")
    print("  Or use --force to move it (with confirmation).")
    return False


def _relocate_portable_rules(project: Path, sel: Selections) -> None:
    """Remove selected portable rules an older foundry deployed to
    .claude/rules/ — they are in AGENTS.md now, and Claude Code loads both,
    so keeping them would load every rule twice."""
    rules_dir = project / ".claude" / "rules"
    names = {rule for rule in sel.deployed_rules if rule not in CLAUDE_ONLY_RULES}
    names |= {f"{category}-{rule}" for category, rules in sel.modular.items() for rule in rules}
    moved = sorted(name for name in names if (rules_dir / name).is_file())
    for name in moved:
        (rules_dir / name).unlink()
    if moved:
        print(f"  Moved {len(moved)} rule(s) from .claude/rules/ to AGENTS.md: {', '.join(moved)}")


class ClaudeAdapter(CliAdapter):
    id = "claude"
    display_name = "Claude Code"
    shared_outputs = frozenset({AGENTS_MD, MCP_JSON})

    def config_root(self, project: Path) -> Path:
        return project / ".claude"

    def supported_artifacts(self) -> set[str]:
        return {"rules", "mcp", "agents", "skills", "commands", "hooks",
                "plugins", "learned", "private-sources"}

    def skipped(self, sel: Selections) -> list[Skipped]:
        # Claude-only rules reach Claude Code through .claude/rules/.
        return []

    def undeploy(self, project: Path, ctx: DeployContext) -> None:
        print("  Claude Code is no longer a target; its config (.claude/) was left in "
              "place. If you remove it, keep .claude/setup-manifest.json and .claude/VERSION — "
              "the foundry uses them for every target.")

    def deploy(self, project: Path, sel: Selections, ctx: DeployContext) -> DeployResult:
        # Runs before any other adapter writes, so declining here changes nothing.
        if not _may_move_claude_md(project, ctx):
            return DeployResult(ok=False)
        version = _installed_claude_version()
        if version and version < AGENTS_MD_SINCE:
            print(f"  ⚠ Claude Code {'.'.join(map(str, version))} doesn't read AGENTS.md — "
                  f"update to {'.'.join(map(str, AGENTS_MD_SINCE))} or later (`claude update`)")

        claude_dir = project / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)

        # Rules: only the Claude-only ones; the portable ones are in AGENTS.md
        _relocate_portable_rules(project, sel)
        copy_rules(project, [r for r in sel.base if r in CLAUDE_ONLY_RULES], {},
                   ctx.private_prefixes)

        # Agents
        if sel.agents:
            copy_agents(project, sel.agents, ctx.private_prefixes)

        # Commands (pass selected skills so skill commands are conditionally included)
        copy_commands(project, sel.skills, ctx.private_prefixes)

        # Skills
        if sel.skills:
            copy_skills(project, sel.skills, ctx.private_prefixes)

        # Learned Skills
        if sel.learned:
            copy_learned_skills(project, sel.learned)

        # Hooks
        copy_hooks(project, sel.hooks)

        # settings.json
        settings = generate_settings_json(sel.hooks, sel.plugins)
        (claude_dir / "settings.json").write_text(
            json.dumps(settings, indent=2) + "\n", encoding='utf-8')

        # MCP servers: .mcp.json is a shared output (Copilot reads it too),
        # written once by the orchestrator after every adapter has run.

        # ── Private Sources ──
        private_sources: list[dict] = []
        cli_private_sources = ctx.cli_private_sources or []

        if cli_private_sources:
            # CLI --private/--prefix flags take precedence
            for src_path_str, prefix in cli_private_sources:
                source_path = Path(src_path_str).resolve()
                if not source_path.is_dir():
                    print(f"  Private source not a directory: {source_path}")
                    continue
                err = validate_prefix(prefix, [s["prefix"] for s in private_sources])
                if err:
                    print(f"  Invalid prefix '{prefix}': {err}")
                    continue
                content = discover_private_content(source_path)
                # Select all discovered content
                selections = content
                clean_private_files(project, prefix)
                deployed = deploy_private_source(project, source_path, prefix, selections)
                total = sum(len(v) for v in deployed.values())
                print(f"  ✓ Private source deployed: {prefix} ({total} files)")
                private_sources.append({"path": str(source_path), "prefix": prefix, **deployed})
        elif ctx.pending_private:
            # Deploy private sources collected during interactive step loop
            for ps in ctx.pending_private:
                clean_private_files(project, ps["prefix"])
                deployed = deploy_private_source(
                    project, ps["source_path"], ps["prefix"], ps["selections"])
                total = sum(len(v) for v in deployed.values())
                print(f"  ✓ Private source deployed: {ps['prefix']} ({total} files)")
                private_sources.append({
                    "path": str(ps["source_path"]), "prefix": ps["prefix"], **deployed,
                })
        elif ctx.existing_private:
            # Non-interactive: re-deploy from manifest
            private_sources = redeploy_private_sources(project, ctx.existing_private)

        # Instructions: AGENTS.md is a shared output, written after every adapter ran.
        return DeployResult(ok=True, private_sources=private_sources)
