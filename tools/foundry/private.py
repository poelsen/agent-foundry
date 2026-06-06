"""Private config source discovery, validation, and deployment."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .registry import BASE_RULES, MODULAR_RULES

# Reserved prefixes that would collide with foundry file names
_RESERVED_PREFIXES: set[str] | None = None


def _get_reserved_prefixes() -> set[str]:
    """Build set of reserved prefixes from base rules and modular categories."""
    global _RESERVED_PREFIXES
    if _RESERVED_PREFIXES is None:
        _RESERVED_PREFIXES = (
            {r.replace(".md", "") for r in BASE_RULES}
            | set(MODULAR_RULES.keys())
        )
    return _RESERVED_PREFIXES


def validate_prefix(prefix: str, existing_prefixes: list[str]) -> str | None:
    """Validate a private source prefix. Returns error message or None if valid."""
    if not re.match(r'^[a-z][a-z0-9-]*$', prefix):
        return "Prefix must start with a letter, contain only lowercase alphanumeric and hyphens"
    if prefix in _get_reserved_prefixes():
        return f"'{prefix}' conflicts with a foundry name"
    if prefix in existing_prefixes:
        return f"'{prefix}' is already registered"
    return None


def discover_private_content(source_path: Path) -> dict[str, list[str]]:
    """Scan a private source directory for deployable content."""
    content: dict[str, list[str]] = {
        "rules": [], "commands": [], "skills": [], "agents": [], "hooks": [],
    }
    # Rules: rule-library/**/*.md → "category/name.md"
    lib = source_path / "rule-library"
    if lib.is_dir():
        for cat_dir in sorted(lib.iterdir()):
            if cat_dir.is_dir():
                for f in sorted(cat_dir.iterdir()):
                    if f.suffix == ".md":
                        content["rules"].append(f"{cat_dir.name}/{f.name}")
    # Commands: commands/*.md
    cmd_dir = source_path / "commands"
    if cmd_dir.is_dir():
        for f in sorted(cmd_dir.iterdir()):
            if f.suffix == ".md":
                content["commands"].append(f.name)
    # Skills: skills/*/ (directories)
    skill_dir = source_path / "skills"
    if skill_dir.is_dir():
        for d in sorted(skill_dir.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                content["skills"].append(d.name)
    # Agents: agents/*.md
    agent_dir = source_path / "agents"
    if agent_dir.is_dir():
        for f in sorted(agent_dir.iterdir()):
            if f.suffix == ".md":
                content["agents"].append(f.name)
    # Hooks: hooks/library/*.sh
    hook_dir = source_path / "hooks" / "library"
    if hook_dir.is_dir():
        for f in sorted(hook_dir.iterdir()):
            if f.suffix == ".sh":
                content["hooks"].append(f.name)
    return content


def clean_private_files(project: Path, prefix: str) -> None:
    """Remove all files/dirs with given prefix from all component dirs."""
    for subdir in ["rules", "agents", "commands"]:
        d = project / ".claude" / subdir
        if d.is_dir():
            for f in d.iterdir():
                if f.is_file() and f.name.startswith(f"{prefix}-"):
                    f.unlink()
    # Skills are directories
    skills_dir = project / ".claude" / "skills"
    if skills_dir.is_dir():
        for d in skills_dir.iterdir():
            if d.is_dir() and d.name.startswith(f"{prefix}-"):
                shutil.rmtree(d)
    # Hooks
    hooks_dir = project / ".claude" / "hooks" / "library"
    if hooks_dir.is_dir():
        for f in hooks_dir.iterdir():
            if f.is_file() and f.name.startswith(f"{prefix}-"):
                f.unlink()


def deploy_private_source(
    project: Path,
    source_path: Path,
    prefix: str,
    selections: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Deploy files from a private source with prefix. Returns deployed selections."""
    deployed: dict[str, list[str]] = {
        "rules": [], "commands": [], "skills": [], "agents": [], "hooks": [],
    }

    # Rules: rule-library/category/name.md → .claude/rules/{prefix}-{name}.md
    for label in selections.get("rules", []):
        parts = label.split("/", 1)
        if len(parts) != 2:
            continue
        category, name = parts
        src = source_path / "rule-library" / category / name
        if src.exists():
            dest = project / ".claude" / "rules" / f"{prefix}-{name}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            deployed["rules"].append(label)

    # Commands: commands/name.md → .claude/commands/{prefix}-{name}.md
    cmd_dir = project / ".claude" / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    for name in selections.get("commands", []):
        src = source_path / "commands" / name
        if src.exists():
            shutil.copy2(src, cmd_dir / f"{prefix}-{name}")
            deployed["commands"].append(name)

    # Skills: skills/name/ → .claude/skills/{prefix}-{name}/
    for name in selections.get("skills", []):
        src = source_path / "skills" / name
        if src.is_dir():
            dest = project / ".claude" / "skills" / f"{prefix}-{name}"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            deployed["skills"].append(name)

    # Agents: agents/name.md → .claude/agents/{prefix}-{name}.md
    agent_dir = project / ".claude" / "agents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    for name in selections.get("agents", []):
        src = source_path / "agents" / name
        if src.exists():
            shutil.copy2(src, agent_dir / f"{prefix}-{name}")
            deployed["agents"].append(name)

    # Hooks: hooks/library/name.sh → .claude/hooks/library/{prefix}-{name}.sh
    for name in selections.get("hooks", []):
        src = source_path / "hooks" / "library" / name
        if src.exists():
            dest = project / ".claude" / "hooks" / "library" / f"{prefix}-{name}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            dest.chmod(dest.stat().st_mode | 0o111)
            deployed["hooks"].append(name)

    return deployed


def redeploy_private_sources(project: Path, sources: list[dict]) -> list[dict]:
    """Non-interactive re-deployment of all private sources from manifest.

    Returns the updated sources list (skipping missing paths).
    """
    result = []
    for source in sources:
        source_path = Path(source["path"])
        prefix = source["prefix"]
        if not source_path.is_dir():
            print(f"  ⚠ Private source missing: {source['path']} (skipped)")
            result.append(source)  # Keep in manifest so user can fix path
            continue
        clean_private_files(project, prefix)
        deployed = deploy_private_source(project, source_path, prefix, source)
        total = sum(len(v) for v in deployed.values())
        print(f"  ✓ Private source re-applied: {prefix} ({total} files)")
        result.append({
            "path": str(source_path),
            "prefix": prefix,
            **deployed,
        })
    return result
