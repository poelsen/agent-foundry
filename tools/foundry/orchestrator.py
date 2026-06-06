"""CLI command entrypoints: version, check, init, update-all, and main()."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from .console import GoBack, QuitSetup, confirm, toggle_menu
from .deploy import (
    copy_agents,
    copy_commands,
    copy_hooks,
    copy_learned_skills,
    copy_rules,
    copy_skills,
    discover_learned_categories,
    generate_settings_json,
    write_mcp_servers,
)
from .detect import detect_languages, detect_platform, detect_templates
from .instructions import (
    generate_claude_foundry_header,
    generate_claude_md,
    has_claude_foundry_header,
    prepend_claude_foundry_header,
    update_claude_foundry_header,
)
from .manifest import (
    discover_projects,
    load_manifest,
    migrate_manifest,
    read_version,
    save_manifest,
)
from .paths import AGENTS_DIR, COMMANDS_DIR, MCP_SERVERS_FILE, REPO_ROOT
from .payload import _install_foundry_payload
from .private import (
    clean_private_files,
    deploy_private_source,
    discover_private_content,
    redeploy_private_sources,
    validate_prefix,
)
from .registry import (
    BASE_RULES,
    FEATURE_REQUIRED_SKILLS,
    FEATURE_SUGGESTED_SKILLS,
    HIDDEN_SKILLS,
    HOOK_SCRIPTS,
    LSP_PLUGINS,
    MODULAR_RULES,
    OPTIONAL_FEATURES,
    SKILL_GROUPS,
    SKILLS,
    WORKFLOW_PLUGINS,
)

__doc_usage__ = """Claude Code per-project setup tool.

Configures a project's .claude/ directory with selected rules, hooks,
agents, skills, plugins, and MCP servers from the claude-foundry repo.
Includes prj-* project management skills.

Usage:
    python3 tools/setup.py init [project_dir]
    python3 tools/setup.py init [project_dir] --private /path/to/source --prefix name
    python3 tools/setup.py update-all
    python3 tools/setup.py check
    python3 tools/setup.py version
"""


def cmd_version() -> None:
    print(f"claude-foundry version: {read_version()}")


def cmd_check() -> None:
    local = read_version()
    print(f"Local repo version: {local}")
    # Try fetching from GitHub
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-remote", "--tags", "origin"],
            capture_output=True, text=True, timeout=10,
        )
        tags = [
            line.split("refs/tags/")[-1].strip()
            for line in result.stdout.strip().splitlines()
            if "refs/tags/" in line and "^{}" not in line
        ]
        if tags:
            latest = sorted(tags)[-1]
            if latest > local:
                print(f"Latest on GitHub: {latest} — update available")
                print(f"  cd {REPO_ROOT} && git pull && python3 tools/setup.py init")
            else:
                print("Up to date.")
        else:
            print("No tags found on remote. Use git log to check for updates.")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Could not check remote: {e}")


def cmd_init(
    project: Path,
    interactive: bool = True,
    force: bool = False,
    cli_private_sources: list[tuple[str, str]] | None = None,
) -> bool:
    """Initialize or update a project. Returns True on success.

    Args:
        project: Path to the project directory
        interactive: Whether to prompt for choices
        force: Force update even if CLAUDE.md has no marker (with confirmation)
        cli_private_sources: List of (path, prefix) tuples from --private/--prefix flags
    """
    version = read_version()
    project = project.resolve()
    project_name = project.name

    print(f"Claude Config Setup v{version}")
    print(f"Project: {project}")
    print()

    # ── Pre-checks ──
    version_file = project / ".claude" / "VERSION"
    if version_file.exists() and interactive:
        existing = version_file.read_text(encoding='utf-8').strip()
        if existing == version:
            if not confirm("Already configured with current version. Reconfigure?", default=False):
                return False
        elif existing < version:
            if not confirm(f"Project configured with {existing}, repo is {version}. Update?"):
                return False
        else:
            print(f"Project version ({existing}) is newer than repo ({version}). Aborting.")
            return False

    # ── Load manifest for defaults ──
    manifest = load_manifest(project)
    if manifest:
        manifest = migrate_manifest(manifest)

    def _manifest_indices(registry_items: list[str], manifest_key: str,
                          manifest_sub: str | None = None) -> set[int]:
        """Compute pre-selected indices from manifest."""
        if not manifest:
            return set()
        saved = manifest.get(manifest_key, []) if not manifest_sub else \
            manifest.get(manifest_key, {}).get(manifest_sub, [])
        return {i for i, item in enumerate(registry_items) if item in saved}

    # ── 1. Detect languages & templates ──
    print("Scanning project...")
    detected_langs = detect_languages(project)
    detected_templates = detect_templates(project)
    detected_platform = detect_platform(project)

    all_detected = detected_langs | detected_templates | detected_platform
    if all_detected:
        print(f"Detected: {', '.join(sorted(r.replace('.md', '') for r in all_detected))}")
    else:
        print("No languages or templates auto-detected.")

    # ── Pre-compute static data ──
    learned_cats = discover_learned_categories()
    agent_files = (sorted(f.name for f in AGENTS_DIR.iterdir() if f.suffix == ".md")
                   if AGENTS_DIR.is_dir() else [])
    hook_names = list(HOOK_SCRIPTS.keys())
    mcp_available = MCP_SERVERS_FILE.exists()
    mcp_names: list[str] = []
    mcp_descs: list[str] = []
    if mcp_available:
        all_mcp_data = json.loads(MCP_SERVERS_FILE.read_text(encoding='utf-8'))["mcpServers"]
        mcp_names = list(all_mcp_data.keys())
        mcp_descs = [f"{k} — {v.get('description', '')}" for k, v in all_mcp_data.items()]
    existing_private = manifest.get("private_sources", []) if manifest else []
    existing_private_prefixes = [s["prefix"] for s in existing_private]
    category_labels = {"lang": "Languages", "templates": "Project Template",
                       "platform": "Platform", "security": "Security Level"}
    modular_categories = ["lang", "templates", "platform", "security"]

    # ── Selection phase (step-based with back/quit for interactive) ──
    STEPS = ["base", *modular_categories,
             "hooks", "agents", "skills", "learned", "plugins", "mcp", "features"]
    if interactive and not cli_private_sources:
        STEPS.append("private")
    saved_steps: dict[str, set[int]] = {}
    saved_plugin_names: set[str] | None = None
    pending_private: list[dict] = []
    step = 0

    def _skip_step(s: str) -> bool:
        return ((s == "learned" and not learned_cats) or
                (s == "mcp" and not mcp_available))

    def _for_detection() -> set[str]:
        """Derive selected_for_detection from current saved state."""
        lr = list(MODULAR_RULES["lang"].keys())
        tr = list(MODULAR_RULES["templates"].keys())
        return ({lr[i] for i in saved_steps.get("lang", set()) if i < len(lr)} |
                {tr[i] for i in saved_steps.get("templates", set()) if i < len(tr)})

    try:
        while step < len(STEPS):
            name = STEPS[step]
            if _skip_step(name):
                step += 1
                continue

            try:
                if name == "base":
                    if "base" in saved_steps:
                        defaults = saved_steps["base"]
                    elif manifest:
                        defaults = _manifest_indices(BASE_RULES, "base_rules")
                    else:
                        defaults = set(range(len(BASE_RULES)))
                    if interactive:
                        saved_steps["base"] = toggle_menu(
                            "Base Rules (all recommended)", BASE_RULES, defaults)
                    else:
                        saved_steps["base"] = defaults

                elif name in modular_categories:
                    rules = list(MODULAR_RULES[name].keys())
                    if not rules:
                        step += 1
                        continue
                    if name in saved_steps:
                        auto = saved_steps[name]
                    elif manifest:
                        auto = _manifest_indices(rules, "modular_rules", name)
                    else:
                        auto = set()
                        for i, rule in enumerate(rules):
                            if (name == "lang" and rule in detected_langs) or (name == "templates" and rule in detected_templates) or (name == "platform" and rule in detected_platform):
                                auto.add(i)
                    required = name == "security"
                    label = category_labels.get(name, name)
                    if interactive:
                        saved_steps[name] = toggle_menu(
                            f"{label}" + (" (select exactly one)" if required else ""),
                            [f"{rule}" for rule in rules], auto,
                            required_one=required)
                    else:
                        saved_steps[name] = auto

                elif name == "hooks":
                    sfd = _for_detection()
                    if "hooks" in saved_steps:
                        auto = saved_steps["hooks"]
                    elif manifest:
                        auto = _manifest_indices(hook_names, "hooks")
                    else:
                        auto = set()
                        for i, script in enumerate(hook_names):
                            meta = HOOK_SCRIPTS[script]
                            if any(lang in sfd for lang in meta["langs"]):
                                auto.add(i)
                    if interactive:
                        saved_steps["hooks"] = toggle_menu(
                            "Hooks (auto-selected by language)",
                            [f"{s} — {HOOK_SCRIPTS[s]['desc']}" for s in hook_names],
                            auto)
                    else:
                        saved_steps["hooks"] = auto

                elif name == "agents":
                    sfd = _for_detection()
                    if "agents" in saved_steps:
                        auto = saved_steps["agents"]
                    elif manifest:
                        auto = _manifest_indices(agent_files, "agents")
                    else:
                        auto = set()
                        for i, af in enumerate(agent_files):
                            for lang in sfd:
                                lang_key = lang.replace(".md", "")
                                if f"-{lang_key}." in af or af.startswith(f"{lang_key}."):
                                    auto.add(i)
                            if (any(r in sfd for r in ["react-app.md", "nodejs.md"])
                                    and "typescript" in af):
                                auto.add(i)
                            if "desktop-gui-qt.md" in sfd and "python-qt" in af:
                                auto.add(i)
                    if interactive:
                        saved_steps["agents"] = toggle_menu("Agents", agent_files, auto)
                    else:
                        saved_steps["agents"] = auto

                elif name == "skills":
                    sfd = _for_detection()
                    if "skills" in saved_steps:
                        auto = saved_steps["skills"]
                    elif manifest:
                        auto = _manifest_indices(SKILLS, "skills")
                    else:
                        auto = set()
                    # Detection-based auto-selects (platform-specific)
                    for i, skill in enumerate(SKILLS):
                        if skill == "gui-threading" and "desktop-gui-qt.md" in sfd:
                            auto.add(i)
                        if skill == "python-qt-gui" and "desktop-gui-qt.md" in sfd:
                            auto.add(i)
                    # Default-on individual skills (the small always-useful set)
                    always_on = ("update-foundry", "learn", "learn-recall", "snapshot-list",
                                 "private-list", "private-remove", "review-process",
                                 "copilot-cli")
                    for i, skill in enumerate(SKILLS):
                        if skill in always_on:
                            auto.add(i)
                    # Default-on groups (megamind + prj)
                    default_groups = ("Megamind Reasoning", "Project Management")
                    for group_name in default_groups:
                        for skill in SKILL_GROUPS[group_name]:
                            if skill in SKILLS:
                                auto.add(SKILLS.index(skill))

                    # Build the visible menu: groups first, then ungrouped
                    # skills; HIDDEN_SKILLS never appear (none today).
                    grouped_members = {s for members in SKILL_GROUPS.values() for s in members}
                    ungrouped = [s for s in SKILLS
                                 if s not in grouped_members and s not in HIDDEN_SKILLS]

                    visible_items: list[str] = []
                    visible_to_skills: list[list[str]] = []
                    for group_name, members in SKILL_GROUPS.items():
                        visible_items.append(f"{group_name} ({len(members)} skills)")
                        visible_to_skills.append(list(members))
                    for skill in ungrouped:
                        visible_items.append(skill)
                        visible_to_skills.append([skill])

                    # Initial visible selection: a group is "on" when ANY of its
                    # members are in auto — tolerates legacy manifests where
                    # users may have had partial group selections.
                    auto_visible: set[int] = set()
                    for vi, skills in enumerate(visible_to_skills):
                        if any(SKILLS.index(s) in auto for s in skills):
                            auto_visible.add(vi)

                    if interactive:
                        chosen_visible = toggle_menu("Skills", visible_items, auto_visible)
                    else:
                        chosen_visible = auto_visible

                    # Project visible-menu decisions back onto SKILLS indices.
                    final = set(auto)
                    for vi, skills in enumerate(visible_to_skills):
                        idxs = {SKILLS.index(s) for s in skills}
                        if vi in chosen_visible:
                            final |= idxs
                        else:
                            final -= idxs
                    saved_steps["skills"] = final

                elif name == "learned":
                    if "learned" in saved_steps:
                        auto = saved_steps["learned"]
                    elif manifest:
                        auto = _manifest_indices(learned_cats, "learned_categories")
                    else:
                        auto = set(range(len(learned_cats)))
                    if interactive:
                        saved_steps["learned"] = toggle_menu(
                            "Learned Skills (categories)", learned_cats, auto)
                    else:
                        saved_steps["learned"] = auto

                elif name == "plugins":
                    sfd = _for_detection()
                    lsp_plugins: list[tuple[str, str]] = []
                    seen_lsp: set[str] = set()
                    for lang in sfd:
                        if lang in LSP_PLUGINS:
                            plugin, binary = LSP_PLUGINS[lang]
                            if plugin not in seen_lsp:
                                lsp_plugins.append((plugin, binary))
                                seen_lsp.add(plugin)
                    all_plugins = ([(p, f"LSP: {b}") for p, b in lsp_plugins] +
                                   [(p, d) for p, d in WORKFLOW_PLUGINS])
                    plugin_display = [f"{p} — {d}" for p, d in all_plugins]
                    if saved_plugin_names is not None:
                        auto = {i for i, (p, _) in enumerate(all_plugins)
                                if p in saved_plugin_names}
                    elif manifest:
                        sp = manifest.get("plugins", [])
                        auto = {i for i, (p, _) in enumerate(all_plugins) if p in sp}
                    else:
                        auto = set(range(len(all_plugins)))
                    result = toggle_menu("Plugins", plugin_display, auto) if interactive else auto
                    saved_steps["plugins"] = result
                    saved_plugin_names = {all_plugins[i][0] for i in result
                                          if i < len(all_plugins)}

                elif name == "mcp":
                    if "mcp" in saved_steps:
                        auto = saved_steps["mcp"]
                    elif manifest:
                        sm = manifest.get("mcp_servers", [])
                        auto = {i for i, n in enumerate(mcp_names) if n in sm}
                    else:
                        auto = set()
                    if interactive:
                        saved_steps["mcp"] = toggle_menu(
                            "MCP Servers (optional)", mcp_descs, auto)
                    else:
                        saved_steps["mcp"] = auto

                elif name == "features":
                    # Opt-in tooling (default OFF). Each feature excludes a
                    # chunk of tools/ from the foundry self-copy unless the
                    # user deliberately checks it here.
                    feat_labels = [f"{label} — {desc}"
                                   for _, label, desc in OPTIONAL_FEATURES]
                    if "features" in saved_steps:
                        auto = saved_steps["features"]
                    elif manifest:
                        sel = set(manifest.get("features", []))
                        auto = {i for i, (k, _, _) in enumerate(OPTIONAL_FEATURES)
                                if k in sel}
                    else:
                        auto = set()
                    if interactive:
                        saved_steps["features"] = toggle_menu(
                            "Optional Features", feat_labels, auto)
                    else:
                        saved_steps["features"] = auto
                    # Auto-suggest associated skills when a feature is ON.
                    # (User can still uncheck them after.)
                    sel_keys = {OPTIONAL_FEATURES[i][0]
                                for i in saved_steps["features"]}
                    if "skills" in saved_steps:
                        for key in sel_keys:
                            # Suggested + required skills both pre-checked here.
                            # The required reconciliation later in finalize will
                            # also re-add required skills if the user unchecks
                            # them — the feature is non-functional without them.
                            for skill in (
                                FEATURE_SUGGESTED_SKILLS.get(key, [])
                                + FEATURE_REQUIRED_SKILLS.get(key, [])
                            ):
                                if skill in SKILLS:
                                    saved_steps["skills"].add(SKILLS.index(skill))

                elif name == "private":
                    # Interactive-only: collect private sources (deployment deferred)
                    while True:
                        label = f" ({len(pending_private)} added)" if pending_private else ""
                        raw = input(
                            f"\nAdd a private config source?{label}"
                            " (path, [b]ack, [q]uit, Enter=done): "
                        ).strip()
                        if not raw:
                            break
                        if raw.lower() in ("b", "back"):
                            raise GoBack()
                        if raw.lower() in ("q", "quit"):
                            raise QuitSetup()
                        source_path = Path(raw).expanduser().resolve()
                        if not source_path.is_dir():
                            print(f"  Not a directory: {source_path}")
                            continue
                        default_prefix = re.sub(
                            r'[^a-z0-9-]', '-', source_path.name.lower(),
                        ).strip('-') or "private"
                        try:
                            prefix_raw = input(f"  Prefix [{default_prefix}]: ").strip()
                            if prefix_raw.lower() in ("q", "quit"):
                                raise QuitSetup()
                            if prefix_raw.lower() in ("b", "back"):
                                continue  # Back to path prompt
                            prefix = prefix_raw or default_prefix
                            all_prefixes = (
                                [s["prefix"] for s in pending_private]
                                + existing_private_prefixes
                            )
                            err = validate_prefix(prefix, all_prefixes)
                            if err:
                                print(f"  Invalid prefix: {err}")
                                continue
                            content = discover_private_content(source_path)
                            if not any(content.values()):
                                print(f"  No deployable content found in {source_path}")
                                continue
                            all_items: list[str] = []
                            item_map: list[tuple[str, str]] = []
                            for comp_type in ["rules", "commands", "skills", "agents", "hooks"]:
                                for item in content[comp_type]:
                                    all_items.append(f"[{comp_type}] {item}")
                                    item_map.append((comp_type, item))
                            selected_prv = toggle_menu(
                                f"Private Source: {prefix}",
                                all_items,
                                set(range(len(all_items))),
                            )
                            selections: dict[str, list[str]] = {
                                "rules": [], "commands": [], "skills": [],
                                "agents": [], "hooks": [],
                            }
                            for idx in sorted(selected_prv):
                                comp_type, item = item_map[idx]
                                selections[comp_type].append(item)
                            if not any(selections.values()):
                                print("  No items selected.")
                                continue
                            pending_private.append({
                                "source_path": source_path,
                                "prefix": prefix,
                                "selections": selections,
                            })
                            print(f"  ✓ Private source queued: {prefix}")
                        except GoBack:
                            continue  # GoBack from toggle → back to path prompt

                step += 1

            except GoBack:
                step -= 1
                while step >= 0 and _skip_step(STEPS[step]):
                    step -= 1
                step = max(0, step)

    except QuitSetup:
        print("\nSetup cancelled.")
        return False

    # ── Derive final selections ──
    selected_base = [BASE_RULES[i] for i in sorted(saved_steps.get("base", set()))]
    selected_modular: dict[str, list[str]] = {}
    for cat in modular_categories:
        rules = list(MODULAR_RULES[cat].keys())
        chosen = [rules[i] for i in sorted(saved_steps.get(cat, set()))]
        if chosen:
            selected_modular[cat] = chosen
    selected_langs = set(selected_modular.get("lang", []))
    selected_templates = set(selected_modular.get("templates", []))
    selected_for_detection = selected_langs | selected_templates  # noqa: F841
    selected_hooks = [hook_names[i] for i in sorted(saved_steps.get("hooks", set()))]
    selected_agents = [agent_files[i] for i in sorted(saved_steps.get("agents", set()))]
    selected_skills = [SKILLS[i] for i in sorted(saved_steps.get("skills", set()))]
    selected_learned = ([learned_cats[i] for i in sorted(saved_steps.get("learned", set()))]
                        if learned_cats else [])
    selected_plugins = sorted(saved_plugin_names) if saved_plugin_names else []
    mcp_servers = ([mcp_names[i] for i in sorted(saved_steps.get("mcp", set()))]
                   if mcp_available else [])
    selected_features = [OPTIONAL_FEATURES[i][0]
                         for i in sorted(saved_steps.get("features", set()))]

    # Reconcile feature-required skills: any feature that's enabled MUST
    # have its required skills installed, regardless of what the manifest
    # says. This heals stale manifests from before the skill was declared
    # required (e.g. minimax-delegate enabled before PR #54 added the
    # delegate skill — old manifests don't list it, but the feature is
    # broken without it).
    for feature in selected_features:
        for skill in FEATURE_REQUIRED_SKILLS.get(feature, []):
            if skill not in selected_skills:
                selected_skills.append(skill)

    # ── Pre-check CLAUDE.md for non-interactive mode ──
    claude_md = project / "CLAUDE.md"
    force_merge = False
    if not interactive and claude_md.exists():
        existing_content = claude_md.read_text(encoding='utf-8')
        if not has_claude_foundry_header(existing_content):
            if force:
                # Force flag — ask for confirmation before proceeding
                print("\n  WARNING: CLAUDE.md exists without claude-foundry marker.")
                print("  Force will merge the header into your existing CLAUDE.md.")
                if not confirm("  Proceed with force merge?", default=False):
                    print("  Aborted.")
                    return False
                force_merge = True
            else:
                # Non-interactive and no marker — skip entire project
                print("\n  CLAUDE.md exists without claude-foundry marker — skipping project")
                print("")
                print("  To add the marker, run setup.py init interactively:")
                print(f"    python3 <claude-foundry>/tools/setup.py init {project}")
                print("  Or use --force to merge the header (with confirmation).")
                return False

    # ── Generate ──
    print("\nGenerating project configuration...")

    # Collect private prefixes (existing + pending) so foundry cleanup skips them
    private_prefixes = existing_private_prefixes + [s["prefix"] for s in pending_private]

    claude_dir = project / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    # VERSION
    (claude_dir / "VERSION").write_text(version + "\n", encoding='utf-8')

    # Rules
    copy_rules(project, selected_base, selected_modular, private_prefixes)

    # Agents
    if selected_agents:
        copy_agents(project, selected_agents, private_prefixes)

    # Commands (pass selected_skills so skill commands are conditionally included)
    copy_commands(project, selected_skills, private_prefixes)

    # Skills
    if selected_skills:
        copy_skills(project, selected_skills, private_prefixes)

    # Learned Skills
    if selected_learned:
        copy_learned_skills(project, selected_learned)

    # Hooks
    copy_hooks(project, selected_hooks)

    # settings.json
    settings = generate_settings_json(selected_hooks, selected_plugins)
    (claude_dir / "settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding='utf-8')

    # MCP servers
    if mcp_servers:
        write_mcp_servers(project, mcp_servers)

    # ── Private Sources ──
    private_sources: list[dict] = []
    cli_private_sources = cli_private_sources or []

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
    elif pending_private:
        # Deploy private sources collected during interactive step loop
        for ps in pending_private:
            clean_private_files(project, ps["prefix"])
            deployed = deploy_private_source(
                project, ps["source_path"], ps["prefix"], ps["selections"])
            total = sum(len(v) for v in deployed.values())
            print(f"  ✓ Private source deployed: {ps['prefix']} ({total} files)")
            private_sources.append({
                "path": str(ps["source_path"]), "prefix": ps["prefix"], **deployed,
            })
    elif existing_private:
        # Non-interactive: re-deploy from manifest
        private_sources = redeploy_private_sources(project, existing_private)

    # Save manifest
    manifest_data: dict = {
        "version": version,
        "config_repo": str(REPO_ROOT),
        "repo_url": "poelsen/claude-foundry",
        "base_rules": selected_base,
        "modular_rules": selected_modular,
        "hooks": selected_hooks,
        "agents": selected_agents,
        "skills": selected_skills,
        "learned_categories": selected_learned,
        "plugins": selected_plugins,
        "mcp_servers": mcp_servers,
        "features": selected_features,
    }
    if private_sources:
        manifest_data["private_sources"] = private_sources
    save_manifest(project, manifest_data)

    # Compute deployed rules list for CLAUDE.md header
    deployed_rules = selected_base.copy()
    for rules in selected_modular.values():
        deployed_rules.extend(rules)

    # CLAUDE.md
    claude_md = project / "CLAUDE.md"
    header = generate_claude_foundry_header(deployed_rules, selected_langs)

    if claude_md.exists():
        existing_content = claude_md.read_text(encoding='utf-8')
        lines = existing_content.count("\n")
        chars = len(existing_content)

        if has_claude_foundry_header(existing_content):
            # Has marker — update header silently
            updated_content = update_claude_foundry_header(existing_content, header)
            claude_md.write_text(updated_content, encoding='utf-8')
            print("  Updated claude-foundry header in CLAUDE.md")
        elif interactive:
            # No marker — offer options
            print(f"\n  CLAUDE.md exists ({lines} lines, {chars} chars)")
            print("  Options:")
            print("    [R] Replace — Generate new CLAUDE.md (saves original as .old)")
            print("    [M] Merge — Prepend claude-foundry header (saves original as .old)")
            print("    [Q] Quit — Abort setup entirely")
            print()
            print("  Note: claude-foundry recommends keeping CLAUDE.md minimal.")
            print("  Move detailed project documentation to docs/ARCHITECTURE.md.")
            print("  The docs/ directory is preferred for project documentation.")
            print()
            choice = input("  Choice [R/M/Q]: ").strip().upper()
            if choice == "Q":
                print("\n  Aborted. No changes made to CLAUDE.md.")
                return False
            elif choice == "R":
                # Save original and replace
                backup = project / "CLAUDE.md.old"
                backup.write_text(existing_content, encoding='utf-8')
                claude_md.write_text(generate_claude_md(project_name, deployed_rules, selected_langs), encoding='utf-8')
                print("  Replaced CLAUDE.md (original saved to CLAUDE.md.old)")
            else:  # M or anything else defaults to Merge
                # Save original and prepend header
                backup = project / "CLAUDE.md.old"
                backup.write_text(existing_content, encoding='utf-8')
                merged = prepend_claude_foundry_header(existing_content, header)
                claude_md.write_text(merged, encoding='utf-8')
                print("  Merged claude-foundry header into CLAUDE.md (original saved to CLAUDE.md.old)")
        elif force_merge:
            # Force merge — prepend header (confirmed earlier)
            backup = project / "CLAUDE.md.old"
            backup.write_text(existing_content, encoding='utf-8')
            merged = prepend_claude_foundry_header(existing_content, header)
            claude_md.write_text(merged, encoding='utf-8')
            print("  Force-merged claude-foundry header into CLAUDE.md (original saved to CLAUDE.md.old)")
        # Note: non-interactive + no marker without force case is handled earlier (skips entire project)
    else:
        claude_md.write_text(generate_claude_md(project_name, deployed_rules, selected_langs), encoding='utf-8')
        print("  Created CLAUDE.md")

    # Summary
    print(f"\n✓ Project configured with claude-foundry v{version}")
    print(f"  Rules: {len(selected_base)} base + {sum(len(v) for v in selected_modular.values())} selected")
    print(f"  Hooks: {len(selected_hooks)}")
    cmd_count = len([f for f in (COMMANDS_DIR).iterdir() if f.suffix == ".md"]) if COMMANDS_DIR.is_dir() else 0
    print(f"  Commands: {cmd_count}")
    print(f"  Agents: {len(selected_agents)}")
    print(f"  Skills: {len(selected_skills)}")
    if selected_learned:
        print(f"  Learned: {len(selected_learned)} categories ({', '.join(selected_learned)})")
    print(f"  Plugins: {len(selected_plugins)}")
    print(f"  MCP servers: {len(mcp_servers)}")
    if private_sources:
        total_private = sum(sum(len(s.get(k, [])) for k in ["rules", "commands", "skills", "agents", "hooks"]) for s in private_sources)
        prefixes = ", ".join(s["prefix"] for s in private_sources)
        print(f"  Private sources: {len(private_sources)} ({prefixes}, {total_private} files)")

    # ── Per-project foundry payload ──────────────────────────────────
    # Drop a self-contained copy of setup.py + the foundry source tarball
    # into <project>/.foundry/ so manual re-runs always match this
    # project's version. Migrates away from the legacy .claude/foundry/
    # exploded tree which Claude could traverse and find duplicates of.
    _install_foundry_payload(project, selected_features)

    return True


def cmd_update_all(force: bool = False) -> None:
    """Batch update all known projects.

    Args:
        force: Force update even if CLAUDE.md has no marker (with confirmation per project)
    """
    version = read_version()
    print(f"Claude Config v{version} — Update All Projects\n")

    projects = discover_projects()
    if not projects:
        print("No projects found in ~/.claude/projects/")
        return

    # Build display list, auto-select those with existing setup
    labels: list[str] = []
    auto: set[int] = set()
    for i, (path, has_setup) in enumerate(projects):
        manifest = load_manifest(path)
        proj_ver = ""
        if has_setup:
            ver_file = path / ".claude" / "VERSION"
            if ver_file.exists():
                proj_ver = ver_file.read_text(encoding='utf-8').strip()
        status = f"v{proj_ver}" if proj_ver else "not configured"
        has_manifest = " +manifest" if manifest else ""
        labels.append(f"{path}  ({status}{has_manifest})")
        if has_setup:
            auto.add(i)

    selected = toggle_menu("Select projects to update", labels, auto)
    if not selected:
        print("No projects selected.")
        return

    # Process each selected project
    results: dict[str, list[str]] = {"updated": [], "interactive": [], "failed": [], "skipped": []}

    for idx in sorted(selected):
        path, has_setup = projects[idx]
        manifest = load_manifest(path)
        print(f"\n{'=' * 60}")
        print(f"Project: {path}")
        print(f"{'=' * 60}")

        if manifest:
            # Non-interactive update using saved choices
            print("Using saved manifest for non-interactive update...")
            try:
                success = cmd_init(path, interactive=False, force=force)
                if success:
                    results["updated"].append(str(path))
                else:
                    results["skipped"].append(str(path))
            except Exception as e:
                print(f"  ✗ Failed: {e}")
                results["failed"].append(str(path))
        else:
            # Interactive init needed
            print("No manifest found — running interactive setup...")
            try:
                success = cmd_init(path, interactive=True, force=force)
                if success:
                    results["interactive"].append(str(path))
                else:
                    results["skipped"].append(str(path))
            except Exception as e:
                print(f"  ✗ Failed: {e}")
                results["failed"].append(str(path))

    # Summary
    print(f"\n{'=' * 60}")
    print("Update All — Summary")
    print(f"{'=' * 60}")
    if results["updated"]:
        print(f"\n  Updated (non-interactive): {len(results['updated'])}")
        for p in results["updated"]:
            print(f"    ✓ {p}")
    if results["interactive"]:
        print(f"\n  Configured (interactive): {len(results['interactive'])}")
        for p in results["interactive"]:
            print(f"    ✓ {p}")
    if results["skipped"]:
        print(f"\n  Skipped: {len(results['skipped'])}")
        for p in results["skipped"]:
            print(f"    — {p}")
    if results["failed"]:
        print(f"\n  Failed: {len(results['failed'])}")
        for p in results["failed"]:
            print(f"    ✗ {p}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc_usage__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "version":
        cmd_version()
    elif command == "check":
        cmd_check()
    elif command == "init":
        interactive = "--non-interactive" not in sys.argv
        force = "--force" in sys.argv
        # Parse --private/--prefix pairs
        private_sources: list[tuple[str, str]] = []
        remaining: list[str] = []
        i = 2
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg in ("--non-interactive", "--force"):
                i += 1
                continue
            if arg == "--private" and i + 1 < len(sys.argv):
                src_path = sys.argv[i + 1]
                # Check if next pair is --prefix
                if i + 2 < len(sys.argv) and sys.argv[i + 2] == "--prefix":
                    if i + 3 < len(sys.argv):
                        prefix = sys.argv[i + 3]
                        i += 4
                    else:
                        print("--prefix requires a value")
                        sys.exit(1)
                else:
                    # Default prefix from directory name
                    prefix = re.sub(
                        r'[^a-z0-9-]', '-', Path(src_path).name.lower(),
                    ).strip('-') or "private"
                    i += 2
                private_sources.append((src_path, prefix))
            else:
                remaining.append(arg)
                i += 1
        project = Path(remaining[0]) if remaining else Path.cwd()
        cmd_init(
            project,
            interactive=interactive,
            force=force,
            cli_private_sources=private_sources or None,
        )
    elif command == "update-all":
        force = "--force" in sys.argv
        cmd_update_all(force=force)
    else:
        print(f"Unknown command: {command}")
        print(__doc_usage__)
        sys.exit(1)
