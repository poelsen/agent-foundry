"""Deployment of rules, agents, commands, skills, hooks, MCP, and settings."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .paths import (
    AGENTS_DIR,
    COMMANDS_DIR,
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
    RETIRED_RULES,
    RETIRED_SKILLS,
    RETIRED_STATE_DIRS,
    SKILLS,
    rule_paths,
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
    RETIRED_RULES and MANIFEST_MIGRATION keys. README.md is never a rule, so
    a project's own README.md in .claude/rules/ is not ours.
    """
    owned = set(BASE_RULES) | RETIRED_RULES
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
# No AI attribution in commits or PRs (matches the git-workflow rule). Object
# form: older Claude Code versions reject a bare boolean and skip the file.
PLUGIN_MARKETPLACE = "claude-plugins-official"
NO_ATTRIBUTION = {"commit": "", "pr": "", "sessionUrl": False}
# Claude Code branches a worktree (and a subagent's) from the default branch
# unless told to use the current HEAD; on a feature branch that is stale code.
WORKTREE_DEFAULTS = {"baseRef": "head"}
BASH_GUARD_SRC = REPO_ROOT / "cli" / "claude" / "hooks" / BASH_GUARD


def generate_settings_json(
    hooks: list[str],
    plugins: list[str],
) -> dict:
    """The foundry's own part of .claude/settings.json."""
    settings: dict = {"bashOutputMaxChars": BASH_OUTPUT_MAX_CHARS,
                      "attribution": dict(NO_ATTRIBUTION),
                      "worktree": dict(WORKTREE_DEFAULTS)}

    # Plugins
    if plugins:
        settings["enabledPlugins"] = {
            f"{p}@{PLUGIN_MARKETPLACE}": True for p in plugins
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



def _is_foundry_hook(handler) -> bool:
    """A hook handler that runs one of the scripts the foundry deploys."""
    command = str(handler.get("command", "")) if isinstance(handler, dict) else ""
    return ".claude/hooks/library/" in command or f".claude/hooks/{BASH_GUARD}" in command


def _without_foundry_hooks(events: dict) -> dict:
    """The project's own hook groups: every foundry handler removed, wherever
    it sits (a user may have added a handler of their own to a foundry group)."""
    kept: dict = {}
    for event, groups in events.items():
        if not isinstance(groups, list):
            kept[event] = groups
            continue
        own = []
        for group in groups:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if isinstance(handlers, list) and handlers:
                remaining = [h for h in handlers if not _is_foundry_hook(h)]
                if not remaining:
                    continue
                if len(remaining) != len(handlers):
                    group = {**group, "hooks": remaining}
            own.append(group)
        if own:
            kept[event] = own
    return kept


def merge_settings_json(existing: dict, generated: dict,
                        owned_plugins: set[str]) -> tuple[dict, list[str]]:
    """Fold the foundry's settings into a project's .claude/settings.json.

    The foundry owns `bashOutputMaxChars`, its `attribution` fields, the hook
    handlers that run its scripts, and the plugins it enabled (`owned_plugins`,
    by name). Its `worktree` values are defaults: one the project set wins.
    Everything else in the file is the project's and is kept.
    Returns the merged settings and the owned plugins that were removed.
    """
    merged = dict(existing)
    merged["bashOutputMaxChars"] = generated["bashOutputMaxChars"]

    attribution = existing.get("attribution")
    merged["attribution"] = {**(attribution if isinstance(attribution, dict) else {}),
                             **generated["attribution"]}

    worktree = existing.get("worktree")
    merged["worktree"] = {**generated["worktree"],
                          **(worktree if isinstance(worktree, dict) else {})}

    current = existing.get("enabledPlugins")
    plugins = dict(current) if isinstance(current, dict) else {}
    wanted = generated.get("enabledPlugins", {})
    owned_ids = {f"{name}@{PLUGIN_MARKETPLACE}" for name in owned_plugins}
    removed = sorted(key for key in plugins if key in owned_ids and key not in wanted)
    for key in removed:
        del plugins[key]
    plugins.update(wanted)
    if plugins:
        merged["enabledPlugins"] = plugins
    else:
        merged.pop("enabledPlugins", None)

    events = existing.get("hooks")
    hooks = _without_foundry_hooks(events if isinstance(events, dict) else {})
    for event, groups in generated["hooks"].items():
        own = hooks.get(event, [])
        hooks[event] = (own if isinstance(own, list) else []) + groups
    merged["hooks"] = hooks
    return merged, removed


def write_settings_json(project: Path, hooks: list[str], plugins: list[str],
                        owned_plugins: set[str]) -> bool:
    """Write the foundry's settings into .claude/settings.json, keeping the
    project's own keys. Returns False when an existing file can't be merged."""
    path = project / ".claude" / "settings.json"
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            print(f"  ⚠ .claude/settings.json doesn't parse ({err}) — settings not written")
            return False
        if not isinstance(existing, dict):
            print("  ⚠ .claude/settings.json has an unexpected shape — settings not written")
            return False
    merged, removed = merge_settings_json(
        existing, generate_settings_json(hooks, plugins), owned_plugins)
    for key in removed:
        print(f"  Removed foundry plugin from .claude/settings.json: {key}")
    if merged != existing:
        path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return True


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
            paths = rule_paths(rule)
            if paths:
                # Claude Code loads a rule with `paths` only once it works on
                # a matching file.
                (rules_dir / dest_name).write_text(
                    f"---\npaths: {json.dumps(list(paths))}\n---\n\n"
                    f"{src.read_text(encoding='utf-8')}", encoding="utf-8")
            else:
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
    or if its stem starts with a skill name followed by a hyphen.
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
    """Copy slash commands to the project and prune retired ones.

    A command named after a skill never deploys (Claude Code exposes every
    skill as ``/name`` already); a sub-command deploys only with its skill.
    """
    selected_skills = selected_skills or []
    private_prefixes = private_prefixes or []
    dest = project / ".claude" / "commands"
    dest.mkdir(parents=True, exist_ok=True)
    # Determine which commands to copy
    eligible = set()
    for src in COMMANDS_DIR.iterdir() if COMMANDS_DIR.is_dir() else ():
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


def copy_skills(
    project: Path,
    skills: list[str],
    private_prefixes: list[str] | None = None,
) -> None:
    private_prefixes = private_prefixes or []
    skills_dir = project / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    wanted = set(skills)
    # Remove stale foundry skills not in current selection. Skip
    # private-prefixed dirs and any skill the foundry never shipped.
    owned = _owned_skill_names()
    foreign: list[str] = []
    for existing in sorted(skills_dir.iterdir()):
        if not existing.is_dir():
            continue
        if existing.name in wanted:
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


def remove_retired_state_dirs(project: Path) -> None:
    """Remove .claude/ dirs that retired commands wrote into (RETIRED_STATE_DIRS).
    Nothing reads them any more; every removal is printed."""
    for name in RETIRED_STATE_DIRS:
        path = project / ".claude" / name
        if path.is_dir():
            shutil.rmtree(path)
            print(f"  Removed retired foundry state: .claude/{name}/")


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
