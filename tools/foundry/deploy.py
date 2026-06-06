"""Deployment of rules, agents, commands, skills, hooks, MCP, and settings."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .paths import (
    AGENTS_DIR,
    COMMANDS_DIR,
    LEARNED_SKILLS_DIR,
    MCP_SERVERS_FILE,
    REPO_ROOT,
)
from .registry import HOOK_SCRIPTS, SKILLS


def generate_settings_json(
    hooks: list[str],
    plugins: list[str],
) -> dict:
    """Build .claude/settings.json content."""
    settings: dict = {}

    # Plugins
    if plugins:
        settings["enabledPlugins"] = {
            f"{p}@claude-plugins-official": True for p in plugins
        }

    # Hooks
    hook_entries: dict[str, list] = {}

    post_hooks = []
    for script in hooks:
        meta = HOOK_SCRIPTS[script]
        # Determine matcher from script name
        if "ruff" in script or "mypy" in script:
            matcher = 'tool == "Edit" && tool_input.file_path matches "\\.py$"'
        elif "prettier" in script:
            matcher = 'tool == "Edit" && tool_input.file_path matches "\\.(ts|tsx|js|jsx)$"'
        elif "tsc" in script:
            matcher = 'tool == "Edit" && tool_input.file_path matches "\\.(ts|tsx)$"'
        elif "cargo" in script:
            matcher = 'tool == "Edit" && tool_input.file_path matches "\\.rs$"'
        else:
            matcher = ""

        post_hooks.append({
            "matcher": matcher,
            "hooks": [{"type": "command", "command": f".claude/hooks/library/{script}"}],
            "description": meta["desc"],
        })

    if post_hooks:
        hook_entries.setdefault("PostToolUse", []).extend(post_hooks)

    if hook_entries:
        settings["hooks"] = hook_entries

    return settings


def copy_rules(
    project: Path,
    base: list[str],
    modular: dict[str, list[str]],
    private_prefixes: list[str] | None = None,
) -> None:
    """Deploy selected rules to .claude/rules/ and remove stale ones.

    Fixes issue #25: when a template migration renames or consolidates
    rule files (e.g. gui.md + python-qt.md + gui-threading.md →
    desktop-gui-qt.md), the old files used to linger in .claude/rules/
    because the previous implementation only wrote new files and never
    removed files that fell out of the selection. The result was Claude
    loading duplicate/conflicting instructions.

    After deploying the current selection, we now iterate the rules dir
    and remove any .md file that is (a) not in the current selection
    and (b) not prefixed with a private source prefix. Private-prefixed
    files are preserved so private config sources aren't clobbered by
    foundry updates.
    """
    private_prefixes = private_prefixes or []
    rules_dir = project / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    # Track every filename we deploy in this run. Anything in the rules
    # dir NOT in this set (and not private-prefixed) gets cleaned up
    # below as a stale file from a previous selection.
    deployed: set[str] = set()

    # Base rules
    for rule in base:
        src = REPO_ROOT / "common" / "rules" / rule
        if src.exists():
            shutil.copy2(src, rules_dir / rule)
            deployed.add(rule)

    # Modular rules (flatten into same dir; prefix with category only
    # on name collision with a base rule we just copied).
    for category, rules in modular.items():
        for rule in rules:
            src = REPO_ROOT / "common" / "rule-library" / category / rule
            if not src.exists():
                continue
            collision = rule in base and (rules_dir / rule).exists()
            dest_name = f"{category}-{rule}" if collision else rule
            shutil.copy2(src, rules_dir / dest_name)
            deployed.add(dest_name)

    # Cleanup pass: remove any .md rule file that isn't in the current
    # deployment and isn't owned by a private source prefix.
    for existing in rules_dir.iterdir():
        if not existing.is_file() or existing.suffix != ".md":
            continue
        if existing.name in deployed:
            continue
        if any(existing.name.startswith(f"{p}-") for p in private_prefixes):
            continue
        existing.unlink()


def copy_agents(
    project: Path,
    agents: list[str],
    private_prefixes: list[str] | None = None,
) -> None:
    private_prefixes = private_prefixes or []
    dest = project / ".claude" / "agents"
    dest.mkdir(parents=True, exist_ok=True)
    # Remove stale agents not in current selection (skip private-prefixed files)
    wanted = set(agents)
    for existing in dest.iterdir():
        if existing.suffix == ".md" and existing.name not in wanted:
            if any(existing.name.startswith(f"{p}-") for p in private_prefixes):
                continue
            existing.unlink()
    for agent in agents:
        src = AGENTS_DIR / agent
        if src.exists():
            shutil.copy2(src, dest / agent)


def _command_skill_parent(command_stem: str) -> str | None:
    """Return the parent skill name for a command, or None if not skill-associated.

    A command is skill-associated if its stem matches a skill name exactly,
    or if its stem starts with a skill name followed by a hyphen (e.g.,
    'update-foundry-check' belongs to the 'update-foundry' skill).
    """
    if command_stem in SKILLS:
        return command_stem
    # Check for prefix match (longest match first to handle nested names)
    for skill in sorted(SKILLS, key=len, reverse=True):
        if command_stem.startswith(skill + "-"):
            return skill
    return None


def copy_commands(
    project: Path,
    selected_skills: list[str] | None = None,
    private_prefixes: list[str] | None = None,
) -> None:
    """Copy slash commands to the project.

    Skill-associated commands are only copied when the corresponding skill is
    selected. A command is skill-associated if its name matches a skill exactly
    or starts with a skill name (e.g., update-foundry-check → update-foundry).
    """
    if not COMMANDS_DIR.is_dir():
        return
    selected_skills = selected_skills or []
    private_prefixes = private_prefixes or []
    dest = project / ".claude" / "commands"
    dest.mkdir(parents=True, exist_ok=True)
    # Determine which commands to copy
    eligible = set()
    for src in COMMANDS_DIR.iterdir():
        if src.suffix != ".md":
            continue
        parent_skill = _command_skill_parent(src.stem)
        # Skip skill-associated commands unless the parent skill is selected
        if parent_skill and parent_skill not in selected_skills:
            continue
        eligible.add(src.name)
    # Remove stale commands not in eligible set (skip private-prefixed files)
    for existing in dest.iterdir():
        if existing.suffix == ".md" and existing.name not in eligible:
            if any(existing.name.startswith(f"{p}-") for p in private_prefixes):
                continue
            existing.unlink()
    # Copy eligible commands
    for name in eligible:
        shutil.copy2(COMMANDS_DIR / name, dest / name)


def discover_learned_categories() -> list[str]:
    """Return sorted list of learned skill category directories."""
    if not LEARNED_SKILLS_DIR.is_dir():
        return []
    return sorted(
        d.name for d in LEARNED_SKILLS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def copy_learned_skills(project: Path, categories: list[str]) -> None:
    """Deploy selected learned skill categories to the project."""
    if not categories:
        return
    dest_base = project / ".claude" / "skills" / "learned"
    local_base = project / ".claude" / "skills" / "learned-local"

    for cat in categories:
        src = LEARNED_SKILLS_DIR / cat
        if not src.is_dir():
            continue
        dest = dest_base / cat
        dest.mkdir(parents=True, exist_ok=True)
        for skill_file in src.iterdir():
            if skill_file.suffix == ".md":
                # Warn on conflict with project-local skills
                local_conflict = local_base / cat / skill_file.name
                if local_conflict.exists():
                    print(f"  ⚠ Conflict: {skill_file.name} exists in both learned/ and learned-local/{cat}/")
                shutil.copy2(skill_file, dest / skill_file.name)


def copy_skills(
    project: Path,
    skills: list[str],
    private_prefixes: list[str] | None = None,
) -> None:
    private_prefixes = private_prefixes or []
    skills_dir = project / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    wanted = set(skills)
    # Remove stale foundry skills not in current selection.
    # Skip: learned/, learned-local/, and private-prefixed dirs.
    protected = {"learned", "learned-local", "_lib"}
    for existing in skills_dir.iterdir():
        if not existing.is_dir():
            continue
        if existing.name in protected:
            continue
        if any(existing.name.startswith(f"{p}-") for p in private_prefixes):
            continue
        if existing.name not in wanted:
            shutil.rmtree(existing)
    # Copy selected skills
    for skill in skills:
        src = REPO_ROOT / "cli" / "claude" / "skills" / skill
        dest = skills_dir / skill
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
    # Copy shared libraries (e.g., _lib/session-id.sh used by prj-* skills)
    lib_src = REPO_ROOT / "cli" / "claude" / "skills" / "_lib"
    if lib_src.is_dir():
        lib_dest = skills_dir / "_lib"
        if lib_dest.exists():
            shutil.rmtree(lib_dest)
        shutil.copytree(lib_src, lib_dest)


def copy_hooks(project: Path, hooks: list[str]) -> None:
    if hooks:
        lib_dest = project / ".claude" / "hooks" / "library"
        lib_dest.mkdir(parents=True, exist_ok=True)
        for script in hooks:
            src = REPO_ROOT / "cli" / "claude" / "hooks" / "library" / script
            if src.exists():
                dest = lib_dest / script
                shutil.copy2(src, dest)
                dest.chmod(dest.stat().st_mode | 0o111)


def _substitute_placeholders(value):
    """Recursively replace {FOUNDRY_ROOT} with the absolute foundry repo path."""
    if isinstance(value, str):
        return value.replace("{FOUNDRY_ROOT}", str(REPO_ROOT))
    if isinstance(value, list):
        return [_substitute_placeholders(v) for v in value]
    if isinstance(value, dict):
        return {k: _substitute_placeholders(v) for k, v in value.items()}
    return value


def write_mcp_servers(project: Path, servers: list[str]) -> None:
    """Deep-merge selected MCP servers into <project>/.mcp.json.

    Claude Code reads project-scoped MCP servers from <project>/.mcp.json
    (no leading '.claude.' prefix) — the same file `claude mcp add --scope
    project` writes to. We previously wrote to <project>/.claude.json, which
    Claude Code doesn't read for project-scoped MCP, so the registered
    servers were silently invisible to every Claude Code session.

    Migration: if a stale <project>/.claude.json exists with an mcpServers
    field that we wrote earlier, fold its entries into the new .mcp.json
    so users don't lose their selections on re-run, then strip the
    mcpServers key from .claude.json (leaving any unrelated fields alone).
    """
    if not servers or not MCP_SERVERS_FILE.exists():
        return
    all_servers = json.loads(MCP_SERVERS_FILE.read_text(encoding='utf-8'))["mcpServers"]
    selected = {k: v for k, v in all_servers.items() if k in servers}
    # Remove description fields (not valid in mcp.json) and substitute placeholders
    for srv in selected.values():
        srv.pop("description", None)
    selected = _substitute_placeholders(selected)

    mcp_json = project / ".mcp.json"
    data: dict = {}
    if mcp_json.exists():
        try:
            data = json.loads(mcp_json.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            data = {}

    # Migration from the old, broken location: salvage anything we'd
    # written to <project>/.claude.json on a previous foundry version.
    legacy = project / ".claude.json"
    legacy_changed = False
    if legacy.exists():
        try:
            legacy_data = json.loads(legacy.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            legacy_data = {}
        if isinstance(legacy_data, dict) and "mcpServers" in legacy_data:
            data.setdefault("mcpServers", {}).update(legacy_data["mcpServers"])
            legacy_data.pop("mcpServers", None)
            legacy_changed = True
            if legacy_data:
                # Other fields exist — rewrite the legacy file without mcpServers
                legacy.write_text(json.dumps(legacy_data, indent=2) + "\n",
                                  encoding='utf-8')
            else:
                # Legacy file was only mcpServers — remove it entirely
                legacy.unlink()

    data.setdefault("mcpServers", {}).update(selected)
    mcp_json.write_text(json.dumps(data, indent=2) + "\n", encoding='utf-8')

    if legacy_changed:
        print("  Migrated MCP servers from .claude.json → .mcp.json")
