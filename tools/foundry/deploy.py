"""Deployment of rules, agents, commands, skills, hooks, MCP, and settings."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .paths import (
    AGENTS_DIR,
    COMMANDS_DIR,
    LEARNED_SKILLS_DIR,
    MCP_SERVERS_FILE,
    REPO_ROOT,
)
from .registry import (
    BASE_RULES,
    HOOK_SCRIPTS,
    MANIFEST_MIGRATION,
    MODULAR_RULES,
    RETIRED_AGENTS,
    RETIRED_COMMANDS,
    RETIRED_SKILLS,
    SKILLS,
)

# ── Prune safety ────────────────────────────────────────────────────────
#
# Every prune pass below may only delete names it can prove are
# foundry-owned: present in the current catalog (registry + shipped
# files) or explicitly retired. Anything else in .claude/ — a project's
# own skills, commands, rules, or agents — is not the foundry's to
# remove: it stays, and gets reported so the user sees what was left
# alone. Every deletion is printed; nothing is ever removed silently.


def _owned_rule_names() -> set[str]:
    """All rule filenames the foundry ships or ever shipped.

    Modular rules deploy flat as ``<rule>`` or ``<category>-<rule>`` on
    collision, so both forms are owned. Retired names come from
    MANIFEST_MIGRATION keys. common/rules/README.md documents the catalog
    and never deploys, so it is excluded — a project's own README.md in
    .claude/rules/ is not ours.
    """
    owned = set(BASE_RULES)
    base_dir = REPO_ROOT / "common" / "rules"
    if base_dir.is_dir():
        owned |= {
            f.name for f in base_dir.iterdir()
            if f.suffix == ".md" and f.name != "README.md"
        }
    lib_dir = REPO_ROOT / "common" / "rule-library"
    if lib_dir.is_dir():
        for cat_dir in lib_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            for f in cat_dir.iterdir():
                if f.suffix == ".md":
                    owned.add(f.name)
                    owned.add(f"{cat_dir.name}-{f.name}")
    for category, rules in MODULAR_RULES.items():
        for rule in rules:
            owned.add(rule)
            owned.add(f"{category}-{rule}")
    for old_cat, old_rule in MANIFEST_MIGRATION:
        owned.add(old_rule)
        owned.add(f"{old_cat}-{old_rule}")
    return owned


def _owned_agent_names() -> set[str]:
    owned = set(RETIRED_AGENTS)
    if AGENTS_DIR.is_dir():
        owned |= {f.name for f in AGENTS_DIR.iterdir() if f.suffix == ".md"}
    return owned


def _owned_command_names() -> set[str]:
    # <skill>.md wrappers no longer ship (skills auto-register as slash
    # commands) but were deployed by older versions — still ours to prune.
    owned = {f"{skill}.md" for skill in SKILLS} | set(RETIRED_COMMANDS)
    if COMMANDS_DIR.is_dir():
        owned |= {f.name for f in COMMANDS_DIR.iterdir() if f.suffix == ".md"}
    return owned


def _owned_skill_names() -> set[str]:
    owned = set(SKILLS) | set(RETIRED_SKILLS)
    skills_src = REPO_ROOT / "cli" / "claude" / "skills"
    if skills_src.is_dir():
        owned |= {d.name for d in skills_src.iterdir() if d.is_dir()}
    return owned


def _prune_stale_files(
    directory: Path,
    owned: set[str],
    keep: set[str],
    private_prefixes: list[str],
    kind: str,
) -> None:
    """Remove stale foundry-owned .md files from ``directory``.

    A file is deleted only when its name is foundry-owned (``owned``) and
    not part of the current deployment (``keep``). Private-prefixed files
    and anything the foundry can't account for are left in place.
    """
    if not directory.is_dir():
        return
    foreign: list[str] = []
    for existing in sorted(directory.iterdir()):
        if not existing.is_file() or existing.suffix != ".md":
            continue
        if existing.name in keep:
            continue
        if any(existing.name.startswith(f"{p}-") for p in private_prefixes):
            continue
        if existing.name in owned:
            existing.unlink()
            print(f"  Removed stale foundry {kind}: {existing.name}")
        else:
            foreign.append(existing.name)
    if foreign:
        print(f"  Left non-foundry {kind}s untouched: {', '.join(foreign)}")


# Skill directories deploy as-is, minus local-only files: a gitignored .env
# (e.g. a maintainer's API key) and bytecode caches.
SKILL_COPY_IGNORE = shutil.ignore_patterns(".env", "__pycache__", "*.pyc")

HOOK_LIBRARY = REPO_ROOT / "cli" / "claude" / "hooks" / "library"
# Sourced by every hook script to list the edited files (see the script).
HOOK_HELPER = "_edited-files.sh"

# Claude Code matches PostToolUse hooks on the tool name only (a regex), so
# the hook fires for every file edit and each script filters by extension
# itself. The expression matchers used previously (`tool == "Edit" && ...`)
# never matched any tool name, so no foundry hook ever ran.
EDIT_TOOLS_MATCHER = "Edit|MultiEdit|Write"

# Always part of the Claude Code settings: command output over this many
# characters is saved to a file and Claude gets a 2 KB preview plus the path
# (Claude Code's default is 30,000), and a PreToolUse hook blocks `cat` of
# large files. Together they keep shell output from flooding the context,
# which would bring on compaction and lose detail sooner.
BASH_OUTPUT_MAX_CHARS = 16_000
BASH_GUARD = "bash-output-guard.py"
BASH_GUARD_SRC = REPO_ROOT / "cli" / "claude" / "hooks" / BASH_GUARD


def generate_settings_json(
    hooks: list[str],
    plugins: list[str],
) -> dict:
    """Build .claude/settings.json content."""
    settings: dict = {"bashOutputMaxChars": BASH_OUTPUT_MAX_CHARS}

    # Plugins
    if plugins:
        settings["enabledPlugins"] = {
            f"{p}@claude-plugins-official": True for p in plugins
        }

    # Hooks
    hook_entries: dict[str, list] = {"PreToolUse": [{
        "matcher": "Bash",
        "hooks": [{"type": "command",
                   "command": f'"$CLAUDE_PROJECT_DIR"/.claude/hooks/{BASH_GUARD}',
                   "timeout": 10}],
        "description": "Blocks cat of large files (use Read with offset/limit)",
    }]}

    post_hooks = []
    for script in hooks:
        meta = HOOK_SCRIPTS[script]
        post_hooks.append({
            "matcher": EDIT_TOOLS_MATCHER,
            # Claude Code may run hooks from a subdirectory; anchor to the project.
            "hooks": [{"type": "command",
                       "command": f'"$CLAUDE_PROJECT_DIR"/.claude/hooks/library/{script}'}],
            "description": meta["desc"],
        })

    if post_hooks:
        hook_entries.setdefault("PostToolUse", []).extend(post_hooks)

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

    After deploying the current selection, we iterate the rules dir and
    remove stale foundry rules: .md files that are (a) foundry-owned per
    _owned_rule_names(), (b) not in the current selection, and (c) not
    prefixed with a private source prefix. Rules the foundry never
    shipped are project-owned and are never deleted.
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

    # Cleanup pass: remove stale foundry rules that fell out of the
    # selection. Project-owned rules are never touched.
    _prune_stale_files(rules_dir, _owned_rule_names(), deployed,
                       private_prefixes, "rule")


def copy_agents(
    project: Path,
    agents: list[str],
    private_prefixes: list[str] | None = None,
) -> None:
    private_prefixes = private_prefixes or []
    dest = project / ".claude" / "agents"
    dest.mkdir(parents=True, exist_ok=True)
    # Remove stale foundry agents not in current selection. Project-owned
    # agents and private-prefixed files are never touched.
    _prune_stale_files(dest, _owned_agent_names(), set(agents),
                       private_prefixes, "agent")
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

    Commands whose name matches a skill *exactly* are never deployed: Claude
    Code already exposes every skill as a ``/name`` slash command, so shipping a
    wrapper command of the same name produces a duplicate entry in the slash
    menu. Only sub-commands (e.g. ``update-foundry-check``) and command-only
    files (e.g. ``snapshot``) are deployed.
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
        # Skip wrappers that duplicate an auto-exposed skill of the same name.
        if src.stem in SKILLS:
            continue
        parent_skill = _command_skill_parent(src.stem)
        # Skip skill-associated commands unless the parent skill is selected
        if parent_skill and parent_skill not in selected_skills:
            continue
        eligible.add(src.name)
    # Remove stale foundry commands not in the eligible set. Project-owned
    # commands and private-prefixed files are never touched.
    _prune_stale_files(dest, _owned_command_names(), eligible,
                       private_prefixes, "command")
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
    # Remove stale foundry skills not in current selection. Skip:
    # learned/, learned-local/, _lib/, private-prefixed dirs — and any
    # skill the foundry never shipped, which is project-owned and not
    # ours to delete.
    protected = {"learned", "learned-local", "_lib"}
    owned = _owned_skill_names()
    foreign: list[str] = []
    for existing in sorted(skills_dir.iterdir()):
        if not existing.is_dir():
            continue
        if existing.name in protected or existing.name in wanted:
            continue
        if any(existing.name.startswith(f"{p}-") for p in private_prefixes):
            continue
        if existing.name in owned:
            shutil.rmtree(existing)
            print(f"  Removed stale foundry skill: {existing.name}")
        else:
            foreign.append(existing.name)
    if foreign:
        print(f"  Left non-foundry skills untouched: {', '.join(foreign)}")
    # Copy selected skills
    for skill in skills:
        src = REPO_ROOT / "cli" / "claude" / "skills" / skill
        dest = skills_dir / skill
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=SKILL_COPY_IGNORE)
    # Copy shared libraries (e.g., _lib/session-id.sh used by prj-* skills)
    lib_src = REPO_ROOT / "cli" / "claude" / "skills" / "_lib"
    if lib_src.is_dir():
        lib_dest = skills_dir / "_lib"
        if lib_dest.exists():
            shutil.rmtree(lib_dest)
        shutil.copytree(lib_src, lib_dest)


def install_hook_scripts(dest: Path, hooks: list[str]) -> None:
    """Copy the selected hook scripts plus the helper they source into ``dest``."""
    if not hooks:
        return
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HOOK_LIBRARY / HOOK_HELPER, dest / HOOK_HELPER)
    for script in hooks:
        src = HOOK_LIBRARY / script
        if src.exists():
            shutil.copy2(src, dest / script)
            (dest / script).chmod((dest / script).stat().st_mode | 0o111)


def copy_hooks(project: Path, hooks: list[str]) -> None:
    install_hook_scripts(project / ".claude" / "hooks" / "library", hooks)
    guard = project / ".claude" / "hooks" / BASH_GUARD
    guard.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASH_GUARD_SRC, guard)
    guard.chmod(guard.stat().st_mode | 0o111)


def _substitute_placeholders(value):
    """Recursively replace {FOUNDRY_ROOT} with the absolute foundry repo path."""
    if isinstance(value, str):
        return value.replace("{FOUNDRY_ROOT}", str(REPO_ROOT))
    if isinstance(value, list):
        return [_substitute_placeholders(v) for v in value]
    if isinstance(value, dict):
        return {k: _substitute_placeholders(v) for k, v in value.items()}
    return value


def selected_mcp_servers(servers: list[str] | None) -> dict[str, dict]:
    """Catalog entries for the selected MCP servers (None: the whole
    catalog), ready to deploy: descriptions dropped (not valid in any CLI's
    config) and {FOUNDRY_ROOT} placeholders substituted."""
    if servers == [] or not MCP_SERVERS_FILE.exists():
        return {}
    all_servers = json.loads(MCP_SERVERS_FILE.read_text(encoding='utf-8'))["mcpServers"]
    selected = {k: v for k, v in all_servers.items() if servers is None or k in servers}
    for srv in selected.values():
        srv.pop("description", None)
    return _substitute_placeholders(selected)


# Catalog placeholders the user is expected to replace (API keys etc.).
_PLACEHOLDER = re.compile(r"^YOUR_[A-Z0-9_]+_HERE$")


def keep_filled_placeholders(rendered: dict, existing: dict | None) -> dict:
    """``rendered`` with the values a user filled in for placeholder env vars
    (e.g. a real FIRECRAWL_API_KEY) carried over from ``existing``."""
    env = rendered.get("env")
    old_env = existing.get("env") if isinstance(existing, dict) else None
    if not isinstance(env, dict) or not isinstance(old_env, dict):
        return rendered
    return {**rendered, "env": {
        k: old_env[k] if _PLACEHOLDER.match(str(v)) and old_env.get(k) not in (None, "") else v
        for k, v in env.items()}}


def _has_filled_placeholder(rendered: dict, existing: dict) -> bool:
    return keep_filled_placeholders(rendered, existing) != rendered


def reconcile_mcp_servers(
    current: dict, catalog: dict[str, dict], selected: list[str], recorded: dict,
) -> tuple[dict, list[str]]:
    """Bring the foundry's catalog servers in ``current`` (an mcpServers map,
    edited in place) up to date with the selection.

    JSON can't carry an ownership marker, so ownership comes from the
    record the foundry keeps (``recorded``: name → the rendering written
    last run, or None for "selected last run, rendering unknown" after an
    upgrade). An entry is the foundry's only if its name is recorded and it
    still equals the recorded or the current rendering, modulo placeholder
    values the user filled in. Equality alone never proves ownership — a
    project may configure a catalog server itself.

    Selected servers are added, or updated when owned (an identical entry
    the project added is adopted). Deselected owned servers are removed —
    unless the user filled in a placeholder such as an API key, which is
    never deleted. Everything else is the project's and is left alone.
    Returns (the renderings now deployed, to record), and the names kept
    because the project owns or changed them.
    """
    deployed: dict[str, dict] = {}
    kept: list[str] = []
    for name, rendered in catalog.items():
        existing = current.get(name)
        if existing is None:
            if name in selected:
                current[name] = rendered
                deployed[name] = rendered
            continue
        candidates = [rendered] if name in recorded else []
        if recorded.get(name) is not None:
            candidates.append(recorded[name])
        owned = any(keep_filled_placeholders(c, existing) == existing for c in candidates)
        if name in selected:
            if owned or keep_filled_placeholders(rendered, existing) == existing:
                current[name] = keep_filled_placeholders(rendered, existing)
                deployed[name] = rendered
            else:
                kept.append(name)
        elif owned:
            if _has_filled_placeholder(rendered, existing):
                print(f"  Kept deselected MCP server {name}: it holds a value you filled in "
                      "(e.g. an API key) — remove it yourself if unwanted")
            else:
                del current[name]
                print(f"  Removed deselected foundry MCP server: {name}")
    return deployed, kept


def write_mcp_servers(project: Path, servers: list[str], state: dict | None = None) -> None:
    """Reconcile the foundry's MCP servers in <project>/.mcp.json.

    ``state`` holds the renderings deployed last run, per config file (it is
    persisted in the manifest); see :func:`reconcile_mcp_servers`.

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
    mcp_json = project / ".mcp.json"
    if not servers and not mcp_json.exists():
        if state is not None:
            state[".mcp.json"] = {}  # nothing of ours there any more
        return
    data: dict = {}
    original: dict | None = None
    if mcp_json.exists():
        try:
            data = json.loads(mcp_json.read_text(encoding='utf-8'))
            original = json.loads(json.dumps(data))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            print(f"  ⚠ .mcp.json doesn't parse ({err}) — MCP servers not written")
            return
        if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
            print("  ⚠ .mcp.json has an unexpected shape — MCP servers not written")
            return

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

    had_servers = "mcpServers" in data
    current = data.setdefault("mcpServers", {})
    before = dict(current)
    deployed, kept = reconcile_mcp_servers(
        current, selected_mcp_servers(None), servers, (state or {}).get(".mcp.json", {}))
    for name in kept:
        print(f"  Kept the project's own mcpServers.{name} in .mcp.json")
    if state is not None:
        state[".mcp.json"] = deployed
    if not current and not had_servers:
        data.pop("mcpServers")
    removed_ours = any(name not in current for name in before)
    if not current and removed_ours and set(data) == {"mcpServers"}:
        mcp_json.unlink()  # it held nothing but the foundry's servers
    elif data != (original or {}):
        mcp_json.write_text(json.dumps(data, indent=2) + "\n", encoding='utf-8')

    if legacy_changed:
        print("  Migrated MCP servers from .claude.json → .mcp.json")
