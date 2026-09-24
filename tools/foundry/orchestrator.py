"""CLI command entrypoints: version, check, init, update-all, and main()."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from .adapters import ADAPTERS, DEFAULT_CLIS, CliAdapter, DeployContext, Selections
from .console import GoBack, QuitSetup, confirm, toggle_menu
from .manifest import (
    discover_projects,
    load_manifest,
    migrate_manifest,
    read_version,
    save_manifest,
)
from .paths import COMMANDS_DIR, REPO_ROOT
from .payload import _install_foundry_payload
from .private import discover_private_content, validate_prefix
from .selection import run_selection
from .shared import deploy_shared_outputs

__doc_usage__ = """agent-foundry per-project setup tool.

Configures a project for one or more coding-agent CLIs with selected
rules, hooks, agents, skills, plugins, and MCP servers. Each chosen CLI's
adapter deploys into its native layout (.claude/ for Claude Code, .codex/
for Codex); files several CLIs read (AGENTS.md, .agents/skills/, .mcp.json)
are written once for all of them.

Usage:
    python3 tools/setup.py init [project_dir]
    python3 tools/setup.py init [project_dir] --clis claude,copilot,codex
    python3 tools/setup.py init [project_dir] --private /path/to/source --prefix name
    python3 tools/setup.py update-all
    python3 tools/setup.py check
    python3 tools/setup.py version
"""


def cmd_version() -> None:
    print(f"agent-foundry version: {read_version()}")


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


def _select_clis(saved: list[str], interactive: bool) -> list[str]:
    """Choose which CLI target(s) to deploy for.

    Non-interactive runs return the saved selection (default ``["claude"]``).
    Interactive runs present a toggle menu of available adapters. Unknown
    ids are reported and dropped. Raises QuitSetup if the user quits.
    """
    available = list(ADAPTERS.keys())
    unknown = [c for c in saved if c not in available]
    if unknown:
        print(f"Unknown CLI target(s) ignored: {', '.join(unknown)} "
              f"(available: {', '.join(available)})")
    # Canonical adapter order, no duplicates: an adapter that can abort (Claude,
    # on an unmarked CLAUDE.md) runs before the others write anything.
    saved = [c for c in available if c in saved] or list(DEFAULT_CLIS)
    if not interactive:
        return saved
    labels = [f"{ADAPTERS[c].display_name} ({c})" for c in available]
    preselected = {i for i, c in enumerate(available) if c in saved}
    try:
        chosen = toggle_menu("Target CLI(s)", labels, preselected, required_one=True)
    except GoBack:
        return saved
    return [available[i] for i in sorted(chosen)] or list(DEFAULT_CLIS)


def _deploy_to_clis(
    project: Path, adapters: list[CliAdapter], sel: Selections, ctx: DeployContext,
    dropped: list[CliAdapter] | None = None,
) -> tuple[bool, list[dict]]:
    """Run each adapter, undeploy CLIs the user dropped as targets, then
    write the shared outputs once for all remaining readers.

    Returns (ok, private_sources). Adapters run in canonical order (Claude
    first), so one that aborts (e.g. the user declined to touch CLAUDE.md)
    stops before any other file is written.
    """
    dropped = dropped or []
    private_sources: list[dict] = []
    for adapter in adapters:
        print(f"\n  → {adapter.display_name}")
        result = adapter.deploy(project, sel, ctx)
        if not result.ok:
            return False, []
        if result.private_sources:
            private_sources = result.private_sources
    for adapter in dropped:
        print(f"\n  → {adapter.display_name} (no longer a target)")
        adapter.undeploy(project, ctx)

    deploy_shared_outputs(project, sel, adapters, dropped, ctx.mcp_state)
    _report_skipped(adapters, sel, ctx)
    return True, private_sources


def _report_skipped(adapters: list[CliAdapter], sel: Selections, ctx: DeployContext) -> None:
    """Say which selected items each target CLI didn't get, and why."""
    lines: list[str] = []
    claude_selected = any(a.id == "claude" for a in adapters)
    for adapter in adapters:
        unsupported: list[str] = []
        for skip in adapter.skipped(sel):
            if skip.claude_only:
                lines.append(f"    {adapter.display_name}: Claude-only {skip.artifact} — "
                             f"{', '.join(skip.items)}")
                if (skip.artifact == "skills" and claude_selected
                        and adapter.reads_claude_skills):
                    lines.append(f"      (note: {adapter.display_name} still loads them "
                                 "from .claude/skills/ on its own)")
            else:
                unsupported.append(f"{skip.artifact} ({len(skip.items)})")
        if unsupported:
            lines.append(f"    {adapter.display_name}: no support for {', '.join(unsupported)}")
    has_private = ctx.cli_private_sources or ctx.pending_private or ctx.existing_private
    if has_private and not any("private-sources" in a.supported_artifacts() for a in adapters):
        lines.append("    Private sources deploy only for Claude Code — not deployed")
    if lines:
        print("\n  Not deployed (the target CLI can't use them):")
        print("\n".join(lines))


def _register_private_sources(
    existing: list[dict], flagged: list[tuple[str, str]],
) -> list[dict]:
    """Manifest entries for private sources nothing deployed this run."""
    registered = list(existing)
    for src_path, prefix in flagged:
        source = Path(src_path).resolve()
        if not source.is_dir() or validate_prefix(prefix, [s["prefix"] for s in registered]):
            print(f"  Private source not registered: {src_path} (prefix {prefix})")
            continue
        registered.append({"path": str(source), "prefix": prefix,
                           **discover_private_content(source)})
        print(f"  Registered private source {prefix} — it deploys once Claude Code is a target")
    return registered


def _mcp_state(manifest: dict | None) -> dict:
    """What the foundry deployed to each MCP config last run. Manifests from
    before it was recorded only know the selection: the foundry wrote those
    names to .mcp.json (the only file it wrote then), rendering unknown."""
    if not manifest:
        return {}
    deployed = manifest.get("deployed_mcp")
    if isinstance(deployed, dict):
        return {file: dict(entries) for file, entries in deployed.items()
                if isinstance(entries, dict)}
    selected = manifest.get("mcp_servers")
    names = [n for n in selected if isinstance(n, str)] if isinstance(selected, list) else []
    return {".mcp.json": dict.fromkeys(names)}


def cmd_init(
    project: Path,
    interactive: bool = True,
    force: bool = False,
    cli_private_sources: list[tuple[str, str]] | None = None,
    clis: list[str] | None = None,
) -> bool:
    """Initialize or update a project. Returns True on success.

    Args:
        project: Path to the project directory
        interactive: Whether to prompt for choices
        force: Force update even if CLAUDE.md has no marker (with confirmation)
        cli_private_sources: List of (path, prefix) tuples from --private/--prefix flags
        clis: Override target CLI ids (e.g. ["claude", "copilot"]); defaults to
            the manifest's saved selection, then ["claude"]
    """
    version = read_version()
    project = project.resolve()
    project_name = project.name

    print(f"Agent Foundry Setup v{version}")
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

    # ── Choose target CLI(s) first, so later menus only offer what they use ──
    unknown = [c for c in clis or [] if c not in ADAPTERS]
    if unknown:
        # A typo must not silently drop (and undeploy) a real target.
        print(f"Unknown CLI target(s): {', '.join(unknown)} (available: {', '.join(ADAPTERS)})",
              file=sys.stderr)
        return False
    saved_clis = clis or (manifest.get("clis", DEFAULT_CLIS) if manifest else DEFAULT_CLIS)
    try:
        selected_clis = _select_clis(saved_clis, interactive)
    except QuitSetup:
        print("\nSetup cancelled.")
        return False
    previous_clis = manifest.get("clis", []) if manifest else []
    dropped_ids = [c for c in ADAPTERS if c in previous_clis and c not in selected_clis]
    if dropped_ids and interactive:
        names = ", ".join(ADAPTERS[c].display_name for c in dropped_ids)
        if not confirm(f"Drop {names}? The foundry's files for it are removed "
                       "(its agents, hooks, managed config).", default=False):
            selected_clis = [c for c in ADAPTERS if c in selected_clis or c in dropped_ids]
            dropped_ids = []
            print(f"Keeping {names} as a target.")
    adapters = [ADAPTERS[c]() for c in selected_clis]
    dropped = [ADAPTERS[c]() for c in dropped_ids]
    consumed = set().union(*(a.supported_artifacts() for a in adapters))

    # ── Selection phase (precompute + step loop + derive) ──
    result = run_selection(project, manifest, interactive, cli_private_sources, consumed)
    if not result.ok:
        return False

    selected_base = result.base
    selected_modular = result.modular
    selected_langs = result.langs
    selected_hooks = result.hooks
    selected_agents = result.agents
    selected_skills = result.skills
    selected_learned = result.learned
    selected_plugins = result.plugins
    mcp_servers = result.mcp_servers
    pending_private = result.pending_private
    existing_private = result.existing_private
    existing_private_prefixes = result.existing_private_prefixes

    # ── Generate ──
    print("\nGenerating project configuration...")

    # Collect private prefixes (existing + pending) so foundry cleanup skips them
    private_prefixes = existing_private_prefixes + [s["prefix"] for s in pending_private]

    sel = Selections(
        base=selected_base, modular=selected_modular, agents=selected_agents,
        skills=selected_skills, learned=selected_learned, hooks=selected_hooks,
        plugins=selected_plugins, mcp_servers=mcp_servers,
        langs=selected_langs, project_name=project_name, version=version,
    )
    ctx = DeployContext(
        interactive=interactive, force=force, private_prefixes=private_prefixes,
        pending_private=pending_private, existing_private=existing_private,
        cli_private_sources=cli_private_sources or [],
        mcp_state=_mcp_state(manifest),
    )

    # Each chosen CLI's adapter renders the selections into its native layout.
    ok, private_sources = _deploy_to_clis(project, adapters, sel, ctx, dropped)
    if not ok:
        return False
    if not any("private-sources" in a.supported_artifacts() for a in adapters):
        # Nothing deployed them this run — keep them registered (plus any
        # given with --private, all content selected as the flag does for
        # Claude Code) so adding Claude Code back later deploys them.
        private_sources = _register_private_sources(existing_private, cli_private_sources or [])

    # Save manifest
    manifest_data: dict = {
        "version": version,
        "config_repo": str(REPO_ROOT),
        "repo_url": "poelsen/agent-foundry",
        "clis": selected_clis,
        "base_rules": selected_base,
        "modular_rules": selected_modular,
        "hooks": selected_hooks,
        "agents": selected_agents,
        "skills": selected_skills,
        "learned_categories": selected_learned,
        "plugins": selected_plugins,
        "mcp_servers": mcp_servers,
    }
    if private_sources:
        manifest_data["private_sources"] = private_sources
    # Always recorded — even when empty — so the next run never mistakes this
    # manifest for one from before ownership was recorded.
    manifest_data["deployed_mcp"] = ctx.mcp_state
    # VERSION for every target: update-all and the version guards key on it.
    (project / ".claude").mkdir(parents=True, exist_ok=True)
    (project / ".claude" / "VERSION").write_text(version + "\n", encoding="utf-8")
    save_manifest(project, manifest_data)

    # Summary
    print(f"\n✓ Project configured with agent-foundry v{version}")
    print(f"  Rules: {len(selected_base)} base + {sum(len(v) for v in selected_modular.values())} selected")
    print(f"  Hooks: {len(selected_hooks)}" + (
        " (each runs only where the project configures its tool — see the README Hooks section)"
        if selected_hooks else ""))
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
    _install_foundry_payload(project)

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
        clis_arg: list[str] | None = None
        remaining: list[str] = []
        i = 2
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg in ("--non-interactive", "--force"):
                i += 1
                continue
            if arg == "--clis" and i + 1 < len(sys.argv):
                clis_arg = [c.strip() for c in sys.argv[i + 1].split(",") if c.strip()]
                i += 2
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
        bad = [c for c in clis_arg or [] if c not in ADAPTERS]
        if clis_arg is not None and (bad or not clis_arg):
            print(f"--clis: unknown CLI target(s) {', '.join(bad) or '(none given)'} "
                  f"(available: {', '.join(ADAPTERS)})", file=sys.stderr)
            sys.exit(2)
        ok = cmd_init(
            project,
            interactive=interactive,
            force=force,
            cli_private_sources=private_sources or None,
            clis=clis_arg,
        )
        # 3 = nothing applied, by design (skipped, declined, cancelled) — so
        # callers such as update-foundry.sh roll back without calling it a
        # failure. Crashes exit 1 (Python's default), usage errors 2.
        sys.exit(0 if ok else 3)
    elif command == "update-all":
        force = "--force" in sys.argv
        cmd_update_all(force=force)
    else:
        print(f"Unknown command: {command}")
        print(__doc_usage__)
        sys.exit(1)
