"""Project detection: languages, templates, platform, file extensions."""

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

from .registry import MODULAR_RULES


def scan_extensions(project: Path) -> set[str]:
    """Scan top 3 levels for file extensions."""
    exts: set[str] = set()
    base_depth = len(project.parts)
    for dirpath, dirnames, filenames in os.walk(project):
        depth = len(Path(dirpath).parts) - base_depth
        if depth >= 3:
            dirnames.clear()
            continue
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "node_modules"]
        for f in filenames:
            ext = Path(f).suffix
            if ext:
                exts.add(ext)
    return exts


def detect_languages(project: Path) -> set[str]:
    """Return set of detected lang rule names."""
    exts = scan_extensions(project)
    detected: set[str] = set()

    for rule, meta in MODULAR_RULES["lang"].items():
        if meta.get("manual"):
            continue
        # Extension match
        for ext in meta.get("detect", []):
            if ext in exts:
                detected.add(rule)
        # Config file match
        for cfg in meta.get("config", []):
            if (project / cfg).exists():
                detected.add(rule)

    return detected


def _read_dep_files(project: Path) -> str:
    """Read dependency files for keyword scanning."""
    text = ""
    for name in ["package.json", "pyproject.toml", "requirements.txt"]:
        p = project / name
        if p.exists():
            with contextlib.suppress(OSError):
                text += p.read_text(encoding='utf-8', errors="ignore")
    return text


def detect_platform(project: Path) -> set[str]:
    detected: set[str] = set()
    if (project / ".github").is_dir():
        detected.add("github.md")
    else:
        # Check git remote for github.com
        try:
            result = subprocess.run(
                ["git", "-C", str(project), "remote", "-v"],
                capture_output=True, text=True, timeout=5,
            )
            if "github.com" in result.stdout:
                detected.add("github.md")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return detected


def detect_templates(project: Path) -> set[str]:
    """Return set of detected template rule names."""
    exts = scan_extensions(project)
    detected: set[str] = set()

    for rule, meta in MODULAR_RULES["templates"].items():
        if meta.get("manual"):
            continue
        for ext in meta.get("detect", []):
            if ext in exts:
                detected.add(rule)
        for cfg in meta.get("config", []):
            if (project / cfg).exists():
                detected.add(rule)

    # Dependency keyword detection
    dep_text = _read_dep_files(project)
    for rule, meta in MODULAR_RULES["templates"].items():
        for kw in meta.get("dep_keywords", []):
            if kw.lower() in dep_text.lower():
                detected.add(rule)

    return detected
