"""CLI command entrypoints: version, check, init, update-all, and main()."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from .adapters import ADAPTERS, DEFAULT_CLIS, DeployContext, Selections
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
from .selection import run_selection

__doc_usage__ = """agent-foundry per-project setup tool.

Configures a project for one or more coding-agent CLIs with selected
rules, hooks, agents, skills, plugins, and MCP servers. Each chosen CLI's
adapter deploys into its native layout (.claude/ for Claude Code,
AGENTS.md for Copilot, ...).

Usage:
    python3 tools/setup.py init [project_dir]
    python3 tools/setup.py init [project_dir] --clis claude,copilot
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
    Interactive runs present a toggle menu of available adapters.
    """
    available = list(ADAPTERS.keys())
    saved = [c for c in saved if c in available] or list(DEFAULT_CLIS)
    if not interactive:
        return saved
    labels = [f"{ADAPTERS[c].display_name} ({c})" for c in available]
    preselected = {i for i, c in enumerate(available) if c in saved}
    try:
        chosen = toggle_menu("Target CLI(s)", labels, preselected, required_one=True)
    except (GoBack, QuitSetup):
        return saved
    return [available[i] for i in sorted(chosen)] or list(DEFAULT_CLIS)


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

    # ── Selection phase (precompute + step loop + derive) ──
    result = run_selection(project, manifest, interactive, cli_private_sources)
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
    selected_features = result.features
    pending_private = result.pending_private
    existing_private = result.existing_private
    existing_private_prefixes = result.existing_private_prefixes

    # ── Choose target CLI(s) ──
    saved_clis = clis or (manifest.get("clis", DEFAULT_CLIS) if manifest else DEFAULT_CLIS)
    selected_clis = _select_clis(saved_clis, interactive)

    # ── Generate ──
    print("\nGenerating project configuration...")

    # Collect private prefixes (existing + pending) so foundry cleanup skips them
    private_prefixes = existing_private_prefixes + [s["prefix"] for s in pending_private]

    sel = Selections(
        base=selected_base, modular=selected_modular, agents=selected_agents,
        skills=selected_skills, learned=selected_learned, hooks=selected_hooks,
        plugins=selected_plugins, mcp_servers=mcp_servers, features=selected_features,
        langs=selected_langs, project_name=project_name, version=version,
    )
    ctx = DeployContext(
        interactive=interactive, force=force, private_prefixes=private_prefixes,
        pending_private=pending_private, existing_private=existing_private,
        cli_private_sources=cli_private_sources or [],
    )

    # Each chosen CLI's adapter renders the selections into its native layout.
    private_sources: list[dict] = []
    for cli_id in selected_clis:
        adapter_cls = ADAPTERS.get(cli_id)
        if adapter_cls is None:
            print(f"  Unknown CLI target '{cli_id}' — skipping")
            continue
        adapter = adapter_cls()
        print(f"\n  → {adapter.display_name}")
        result = adapter.deploy(project, sel, ctx)
        if not result.ok:
            return False
        if result.private_sources:
            private_sources = result.private_sources

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
        "features": selected_features,
    }
    if private_sources:
        manifest_data["private_sources"] = private_sources
    save_manifest(project, manifest_data)

    # Summary
    print(f"\n✓ Project configured with agent-foundry v{version}")
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
        cmd_init(
            project,
            interactive=interactive,
            force=force,
            cli_private_sources=private_sources or None,
            clis=clis_arg,
        )
    elif command == "update-all":
        force = "--force" in sys.argv
        cmd_update_all(force=force)
    else:
        print(f"Unknown command: {command}")
        print(__doc_usage__)
        sys.exit(1)
