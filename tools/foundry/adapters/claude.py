"""Claude Code adapter — deploys into <project>/.claude/ + CLAUDE.md.

This is the full-fidelity target: it consumes every artifact type. The body
is the deployment logic that previously lived inline in cmd_init, moved here
unchanged so Claude Code behavior is identical.
"""

from __future__ import annotations

import json
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
    write_mcp_servers,
)
from ..instructions import (
    generate_agent_foundry_header,
    generate_claude_md,
    has_agent_foundry_header,
    prepend_agent_foundry_header,
    update_agent_foundry_header,
)
from ..private import (
    clean_private_files,
    deploy_private_source,
    discover_private_content,
    redeploy_private_sources,
    validate_prefix,
)
from .base import CliAdapter, DeployContext, DeployResult, Selections


class ClaudeAdapter(CliAdapter):
    id = "claude"
    display_name = "Claude Code"

    def config_root(self, project: Path) -> Path:
        return project / ".claude"

    def supported_artifacts(self) -> set[str]:
        return {"rules", "mcp", "agents", "skills", "commands", "hooks"}

    def deploy(self, project: Path, sel: Selections, ctx: DeployContext) -> DeployResult:
        # ── Pre-check CLAUDE.md for non-interactive mode ──
        claude_md = project / "CLAUDE.md"
        force_merge = False
        if not ctx.interactive and claude_md.exists():
            existing_content = claude_md.read_text(encoding='utf-8')
            if not has_agent_foundry_header(existing_content):
                if ctx.force:
                    # Force flag — ask for confirmation before proceeding
                    print("\n  WARNING: CLAUDE.md exists without agent-foundry marker.")
                    print("  Force will merge the header into your existing CLAUDE.md.")
                    if not confirm("  Proceed with force merge?", default=False):
                        print("  Aborted.")
                        return DeployResult(ok=False)
                    force_merge = True
                else:
                    # Non-interactive and no marker — skip entire project
                    print("\n  CLAUDE.md exists without agent-foundry marker — skipping project")
                    print("")
                    print("  To add the marker, run setup.py init interactively:")
                    print(f"    python3 <agent-foundry>/tools/setup.py init {project}")
                    print("  Or use --force to merge the header (with confirmation).")
                    return DeployResult(ok=False)

        claude_dir = project / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)

        # VERSION
        (claude_dir / "VERSION").write_text(sel.version + "\n", encoding='utf-8')

        # Rules
        copy_rules(project, sel.base, sel.modular, ctx.private_prefixes)

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

        # MCP servers
        if sel.mcp_servers:
            write_mcp_servers(project, sel.mcp_servers)

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

        # ── CLAUDE.md ──
        deployed_rules = sel.deployed_rules
        header = generate_agent_foundry_header(deployed_rules, sel.langs)

        if claude_md.exists():
            existing_content = claude_md.read_text(encoding='utf-8')
            lines = existing_content.count("\n")
            chars = len(existing_content)

            if has_agent_foundry_header(existing_content):
                # Has marker — update header silently
                updated_content = update_agent_foundry_header(existing_content, header)
                claude_md.write_text(updated_content, encoding='utf-8')
                print("  Updated agent-foundry header in CLAUDE.md")
            elif ctx.interactive:
                # No marker — offer options
                print(f"\n  CLAUDE.md exists ({lines} lines, {chars} chars)")
                print("  Options:")
                print("    [R] Replace — Generate new CLAUDE.md (saves original as .old)")
                print("    [M] Merge — Prepend agent-foundry header (saves original as .old)")
                print("    [Q] Quit — Abort setup entirely")
                print()
                print("  Note: agent-foundry recommends keeping CLAUDE.md minimal.")
                print("  Move detailed project documentation to docs/ARCHITECTURE.md.")
                print("  The docs/ directory is preferred for project documentation.")
                print()
                choice = input("  Choice [R/M/Q]: ").strip().upper()
                if choice == "Q":
                    print("\n  Aborted. No changes made to CLAUDE.md.")
                    return DeployResult(ok=False)
                elif choice == "R":
                    # Save original and replace
                    backup = project / "CLAUDE.md.old"
                    backup.write_text(existing_content, encoding='utf-8')
                    claude_md.write_text(
                        generate_claude_md(sel.project_name, deployed_rules, sel.langs),
                        encoding='utf-8')
                    print("  Replaced CLAUDE.md (original saved to CLAUDE.md.old)")
                else:  # M or anything else defaults to Merge
                    # Save original and prepend header
                    backup = project / "CLAUDE.md.old"
                    backup.write_text(existing_content, encoding='utf-8')
                    merged = prepend_agent_foundry_header(existing_content, header)
                    claude_md.write_text(merged, encoding='utf-8')
                    print("  Merged agent-foundry header into CLAUDE.md (original saved to CLAUDE.md.old)")
            elif force_merge:
                # Force merge — prepend header (confirmed earlier)
                backup = project / "CLAUDE.md.old"
                backup.write_text(existing_content, encoding='utf-8')
                merged = prepend_agent_foundry_header(existing_content, header)
                claude_md.write_text(merged, encoding='utf-8')
                print("  Force-merged agent-foundry header into CLAUDE.md (original saved to CLAUDE.md.old)")
            # Note: non-interactive + no marker without force is handled above (skips project)
        else:
            claude_md.write_text(
                generate_claude_md(sel.project_name, deployed_rules, sel.langs),
                encoding='utf-8')
            print("  Created CLAUDE.md")

        return DeployResult(ok=True, private_sources=private_sources)
