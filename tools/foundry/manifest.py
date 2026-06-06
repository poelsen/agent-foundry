"""Manifest persistence, migration, version reading, and project discovery."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .paths import REPO_ROOT
from .registry import MANIFEST_MIGRATION


def read_version() -> str:
    """Read version from VERSION file (tarball) or git tag (clone)."""
    version_file = REPO_ROOT / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding='utf-8').strip()
    # Fall back to latest git tag
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "dev"


def save_manifest(project: Path, manifest: dict) -> None:
    """Save selection manifest for future re-init / update-all."""
    dest = project / ".claude" / "setup-manifest.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, indent=2) + "\n", encoding='utf-8')


def load_manifest(project: Path) -> dict | None:
    """Load saved selection manifest, or None if not present."""
    src = project / ".claude" / "setup-manifest.json"
    if src.exists():
        try:
            return json.loads(src.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def resolve_project_path(encoded_name: str) -> Path | None:
    """Resolve ~/.claude/projects/ encoded dir name to actual filesystem path.

    The encoding replaces both '/' and '_' with '-', so we greedily
    reconstruct by testing which dashes are directory separators vs underscores.
    """
    parts = encoded_name.lstrip("-").split("-")
    if len(parts) < 2:
        return None
    base = Path("/") / parts[0] / parts[1]  # /home/rudm
    remaining = parts[2:]

    def _find(base: Path, remaining: list[str]) -> Path | None:
        if not remaining:
            return base if base.is_dir() else None
        for take in range(1, len(remaining) + 1):
            # Try underscore join
            candidate = base / "_".join(remaining[:take])
            if candidate.is_dir():
                result = _find(candidate, remaining[take:])
                if result:
                    return result
            # Try hyphen join (for dirs with actual hyphens)
            if take > 1:
                candidate = base / "-".join(remaining[:take])
                if candidate.is_dir():
                    result = _find(candidate, remaining[take:])
                    if result:
                        return result
            # Try single part as-is (no join needed for take==1, already covered by underscore)
            if take == 1:
                candidate = base / remaining[0]
                if candidate.is_dir():
                    result = _find(candidate, remaining[1:])
                    if result:
                        return result
        return None

    return _find(base, remaining)


def discover_projects() -> list[tuple[Path, bool]]:
    """Discover known projects from ~/.claude/projects/.

    Returns list of (project_path, has_setup) tuples.
    """
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.is_dir():
        return []
    results = []
    for d in sorted(projects_dir.iterdir()):
        if not d.is_dir():
            continue
        resolved = resolve_project_path(d.name)
        if resolved and resolved.is_dir():
            has_setup = (resolved / ".claude" / "VERSION").exists()
            results.append((resolved, has_setup))
    return results


def migrate_manifest(manifest: dict) -> dict:
    """Migrate a manifest from old category structure to new template structure."""
    modular = manifest.get("modular_rules", {})
    changed = False

    for (old_cat, old_rule), target in MANIFEST_MIGRATION.items():
        if old_cat in modular and old_rule in modular[old_cat]:
            modular[old_cat].remove(old_rule)
            if not modular[old_cat]:
                del modular[old_cat]
            if target is not None:
                new_cat, new_rule = target
                modular.setdefault(new_cat, [])
                if new_rule not in modular[new_cat]:
                    modular[new_cat].append(new_rule)
            changed = True

    # Clean up empty old categories
    for old_cat in ("domain", "arch", "style"):
        if old_cat in modular and not modular[old_cat]:
            del modular[old_cat]
            changed = True

    if changed:
        manifest["modular_rules"] = modular
    return manifest
