#!/usr/bin/env python3
"""Claude Code per-project setup tool.

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

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _ensure_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 so print() emoji never crash on Windows.

    Fixes issue #26: setup.py uses Unicode characters (✓, ✗, ⚠, em dashes,
    etc.) in print() output. On Windows with a default cp1252 console
    encoding, writing those characters raises UnicodeEncodeError and
    crashes the whole install. Reconfiguring the TextIOWrapper to UTF-8
    with ``errors='replace'`` is a strictly additive fix: it has no effect
    where stdout is already UTF-8 (Linux/macOS/WSL/Windows Terminal), and
    it turns crashes into replacement characters on legacy cp1252 consoles.

    This runs unconditionally at module import time. It's safe because:
      1. ``reconfigure()`` is a no-op if encoding is already UTF-8
      2. Any failure (e.g. stdout is piped to a process that can't be
         reconfigured, or stdout was replaced before import) is swallowed
         — the worst case is a legacy cp1252 crash at first emoji, which
         is the pre-fix baseline
      3. ``errors='replace'`` means worst-case a unicode char becomes "?"
         instead of raising
    """
    for stream in (sys.stdout, sys.stderr):
        enc = getattr(stream, "encoding", None)
        if enc is None or enc.lower() == "utf-8":
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # not a TextIOWrapper (e.g. replaced by a test harness)
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            # OSError: underlying buffer not seekable or closed
            # ValueError: invalid encoding name (shouldn't happen with "utf-8")
            pass


_ensure_utf8_stdio()


_TARBALL_MODE = False
_PAYLOAD_TARBALL: Path | None = None


def _resolve_repo_root() -> Path:
    """Resolve REPO_ROOT, switching between source and tarball modes.

    Source mode: setup.py lives at <foundry-repo>/tools/setup.py with
    sibling source dirs (commands/, skills/, ...) one level up.

    Tarball mode: setup.py lives at <project>/.foundry/setup.py with a
    sibling foundry.tar.gz. The tarball is extracted to a tempdir, which
    becomes REPO_ROOT for this run. The tempdir is wiped at process exit.

    Detection: a sibling `foundry.tar.gz` next to setup.py implies tarball
    mode. Anything else implies source mode.
    """
    import atexit
    import tarfile
    import tempfile

    global _TARBALL_MODE, _PAYLOAD_TARBALL
    setup_dir = Path(__file__).resolve().parent
    sibling_tarball = setup_dir / "foundry.tar.gz"

    if sibling_tarball.is_file():
        _TARBALL_MODE = True
        _PAYLOAD_TARBALL = sibling_tarball
        tmpdir = Path(tempfile.mkdtemp(prefix="foundry-"))
        atexit.register(shutil.rmtree, str(tmpdir), ignore_errors=True)
        with tarfile.open(sibling_tarball, "r:gz") as tf:
            try:
                tf.extractall(tmpdir, filter="data")
            except TypeError:
                # Python < 3.12 lacks the filter kwarg
                tf.extractall(tmpdir)
        # Strip a single top-level wrapper dir if present (matches GitHub
        # release tarball convention: `claude-foundry-vX.Y.Z/...`).
        entries = [p for p in tmpdir.iterdir() if not p.name.startswith(".")]
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0]
        return tmpdir

    return setup_dir.parent


REPO_ROOT = _resolve_repo_root()


class GoBack(Exception):
    """User requested to go back to the previous menu."""


class QuitSetup(Exception):
    """User requested to quit setup."""


# ── CLAUDE.md Header ────────────────────────────────────────────────────

CLAUDE_FOUNDRY_MARKER_START = "<!-- claude-foundry -->"
CLAUDE_FOUNDRY_MARKER_END = "<!-- /claude-foundry -->"

CLAUDE_FOUNDRY_HEADER_TEMPLATE = """{marker_start}
## Rules

Read rules in `.claude/rules/` before making changes:
{rules_list}

## Foundry Defaults

```bash
{env_commands}
```

## Architecture

Read `codemaps/INDEX.md` before modifying unfamiliar modules.
Run `/update-codemaps` after significant structural changes.

## Documentation

Read `docs/` for detailed project documentation (if it exists).
- `docs/ARCHITECTURE.md` — design decisions and patterns
- `docs/DEVELOPMENT.md` — setup and workflow guides
{marker_end}
"""

# Only languages with near-universal toolchains get default commands.
# Languages with fragmented build systems (C, C++, Node.js, React) are
# omitted — users add their own commands in the ## Environment section
# above the claude-foundry marker.
ENVIRONMENT_SNIPPETS = {
    "python.md": {
        "setup": "uv sync --extra dev",
        "test": "uv run pytest",
    },
    "rust.md": {
        "setup": "cargo build",
        "test": "cargo test",
    },
    "go.md": {
        "setup": "go mod download",
        "test": "go test ./...",
    },
}

# ── Registry ────────────────────────────────────────────────────────────

BASE_RULES = [
    "coding-style.md", "git-workflow.md", "security.md", "testing.md",
    "architecture.md", "performance.md", "agents.md", "hooks.md", "codemaps.md",
]

MODULAR_RULES = {
    "lang": {
        "python.md": {"detect": [".py"], "config": ["pyproject.toml", "requirements.txt"]},
        "nodejs.md": {"detect": [], "config": ["package.json"]},
        "go.md": {"detect": [".go"], "config": ["go.mod"]},
        "rust.md": {"detect": [".rs"], "config": ["Cargo.toml"]},
        "matlab.md": {"detect": [".m"]},
    },
    "templates": {
        "embedded-c.md": {"manual": True},
        "embedded-dsp.md": {"detect": [], "manual": True},
        "react-app.md": {"detect": [], "dep_keywords": ["react"]},
        "rest-api.md": {"manual": True},
        "desktop-gui-qt.md": {"detect": [], "dep_keywords": ["PySide6", "PyQt"]},
        "library.md": {},
        "scripts.md": {},
        "data-pipeline.md": {},
        "monolith.md": {},
    },
    "platform": {
        "github.md": {"detect_dir": [".github"]},
    },
    "security": {
        "enterprise.md": {}, "internal.md": {}, "sandbox.md": {},
    },
}

# Migration map: (old_category, old_rule) -> (new_category, new_rule) or None
MANIFEST_MIGRATION = {
    ("domain", "embedded.md"): ("templates", "embedded-c.md"),
    ("domain", "dsp-audio.md"): ("templates", "embedded-dsp.md"),
    ("domain", "gui.md"): None,
    ("domain", "gui-threading.md"): ("templates", "desktop-gui-qt.md"),
    ("lang", "c.md"): None,
    ("lang", "c-embedded.md"): ("templates", "embedded-c.md"),
    ("lang", "cpp.md"): None,
    ("lang", "react.md"): ("templates", "react-app.md"),
    ("lang", "python-qt.md"): ("templates", "desktop-gui-qt.md"),
    ("style", "backend.md"): ("templates", "rest-api.md"),
    ("style", "library.md"): ("templates", "library.md"),
    ("style", "scripts.md"): ("templates", "scripts.md"),
    ("style", "data-pipeline.md"): ("templates", "data-pipeline.md"),
    ("arch", "rest-api.md"): ("templates", "rest-api.md"),
    ("arch", "react-app.md"): ("templates", "react-app.md"),
    ("arch", "monolith.md"): ("templates", "monolith.md"),
}

HOOK_SCRIPTS = {
    "ruff-format.sh": {"langs": ["python.md"], "desc": "Python formatting (ruff)"},
    "prettier-format.sh": {"langs": ["react-app.md", "nodejs.md"], "desc": "JS/TS formatting (prettier)"},
    "tsc-check.sh": {"langs": ["react-app.md", "nodejs.md"], "desc": "TypeScript type checking"},
    "mypy-check.sh": {"langs": ["python.md"], "desc": "Python type checking (mypy)"},
    "cargo-check.sh": {"langs": ["rust.md"], "desc": "Rust type checking (cargo check)"},
}

AGENTS_DIR = REPO_ROOT / "agents"
COMMANDS_DIR = REPO_ROOT / "commands"
LEARNED_SKILLS_DIR = REPO_ROOT / "skills" / "learned"

SKILLS = [
    "clickhouse-io", "gui-threading", "python-qt-gui",
    "megamind-deep", "megamind-creative", "megamind-adversarial", "megamind-financial",
    "minimax-multimodal", "delegate", "review-process",
    "update-foundry", "learn", "learn-recall", "snapshot-list",
    "private-list", "private-remove",
    "prj-new", "prj-list", "prj-pause", "prj-resume", "prj-done", "prj-delete",
    "copilot-cli",
]

# Skill groups — presented in the skill selection menu as a single toggle.
# Toggling a group selects/deselects all its member skills together. Member
# skill names are still what gets stored in the manifest, so the format is
# backward-compatible with older installs.
SKILL_GROUPS: dict[str, list[str]] = {
    "Megamind Reasoning": [
        "megamind-deep", "megamind-creative", "megamind-adversarial", "megamind-financial",
    ],
    "Project Management": [
        "prj-new", "prj-list", "prj-pause", "prj-resume", "prj-done", "prj-delete",
    ],
}

# Skills that are never shown in the interactive skill menu. None today —
# kept as an explicit empty set so the menu-build logic stays uniform.
HIDDEN_SKILLS: set[str] = set()

# Optional feature toggles presented in the setup menu. Each tuple is
# (key, label, description). When an entry is selected, the mapped file
# globs under FEATURE_PATHS are included in the foundry self-copy; when
# deselected, they're excluded. Default for every feature is OFF.
OPTIONAL_FEATURES: list[tuple[str, str, str]] = [
    ("minimax-delegate",
     "MiniMax Delegate",
     "Run a secondary Claude Code CLI against MiniMax (skills/delegate/)"),
]

# Relative paths under REPO_ROOT to skip in the foundry self-copy when
# the matching feature key is NOT selected.
FEATURE_PATHS: dict[str, list[str]] = {
    "minimax-delegate": [
        "commands/delegate.md",
        "skills/delegate",
    ],
}

# Skills that should be auto-added to the selection when a feature is
# turned on. Still user-visible; they can uncheck if they really want.
FEATURE_SUGGESTED_SKILLS: dict[str, list[str]] = {
    "minimax-delegate": ["minimax-multimodal"],
}

# Skills that MUST be installed when a feature is enabled — the feature
# is non-functional without them. Auto-added on every run (interactive
# and non-interactive), even if missing from a stale manifest. The user
# cannot remove them while keeping the feature enabled. This heals the
# stale-manifest case where a feature toggle exists but its required
# skills predate when they were declared as required.
FEATURE_REQUIRED_SKILLS: dict[str, list[str]] = {
    "minimax-delegate": ["delegate"],
}

LSP_PLUGINS = {
    "python.md": ("pyright-lsp", "pyright-langserver"),
    "react-app.md": ("typescript-lsp", "typescript-language-server"),
    "nodejs.md": ("typescript-lsp", "typescript-language-server"),
    "rust.md": ("rust-analyzer-lsp", "rust-analyzer"),
    "go.md": ("gopls-lsp", "gopls"),
    "embedded-c.md": ("clangd-lsp", "clangd"),
    "embedded-dsp.md": ("clangd-lsp", "clangd"),
}

WORKFLOW_PLUGINS = [
    ("feature-dev", "7-phase feature workflow"),
    ("pr-review-toolkit", "PR analysis suite"),
    ("code-review", "Automated PR feedback"),
    ("code-simplifier", "Autonomous refactoring"),
]

MCP_SERVERS_FILE = REPO_ROOT / "mcp-configs" / "mcp-servers.json"

# ── Helpers ─────────────────────────────────────────────────────────────


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


def toggle_menu(title: str, items: list[str], selected: set[int],
                required_one: bool = False) -> set[int]:
    """Interactive toggle menu. Returns set of selected indices.

    Raises GoBack if user types 'b', QuitSetup if user types 'q'.
    """
    selected = set(selected)  # Copy to avoid mutating caller's data
    while True:
        print(f"\n=== {title} ===")
        for i, item in enumerate(items):
            mark = "X" if i in selected else " "
            print(f"  [{mark}] {i + 1}. {item}")
        raw = input("Toggle numbers, [b]ack, [q]uit, Enter=confirm: ").strip()
        if not raw:
            if required_one and not selected:
                print("  ⚠ At least one selection required.")
                continue
            return selected
        if raw.lower() in ("b", "back"):
            raise GoBack()
        if raw.lower() in ("q", "quit"):
            raise QuitSetup()
        for token in raw.split():
            try:
                idx = int(token) - 1
                if 0 <= idx < len(items):
                    selected ^= {idx}
            except ValueError:
                pass


def confirm(msg: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{msg} {suffix} ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")


def ask_int(msg: str, default: int) -> int:
    raw = input(f"{msg} [{default}]: ").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


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


def generate_claude_foundry_header(
    deployed_rules: list[str],
    selected_langs: set[str],
) -> str:
    """Generate the claude-foundry header for CLAUDE.md."""
    # Build rules list
    rule_descriptions = {
        # Language/tooling rules
        "python.md": "Python tooling (uv, pytest, ruff)",
        "rust.md": "Rust tooling (cargo, clippy)",
        "go.md": "Go tooling (go mod, golangci-lint)",
        "nodejs.md": "Node.js tooling (npm)",
        "matlab.md": "MATLAB tooling",
        # Project templates
        "embedded-c.md": "Embedded C/C++ (MISRA, memory safety, build)",
        "embedded-dsp.md": "Embedded DSP & Audio (real-time, numerical, HW)",
        "react-app.md": "React application (components, state, UX)",
        "rest-api.md": "REST API backend (layers, reliability, observability)",
        "desktop-gui-qt.md": "Desktop GUI Qt (threading, signals, persistence)",
        "library.md": "Library development (API design, versioning)",
        "scripts.md": "Scripts & CLI (argument parsing, error handling)",
        "data-pipeline.md": "Data pipeline (idempotency, validation, monitoring)",
        "monolith.md": "Monolith architecture (module boundaries, migrations)",
        # Platform rules
        "github.md": "GitHub workflow (gh CLI, PR conventions)",
        # Security rules
        "enterprise.md": "Enterprise security (production, compliance)",
        "internal.md": "Internal security (team tools)",
        "sandbox.md": "Sandbox security (prototyping)",
        # Base rules
        "coding-style.md": "Code style guidelines",
        "git-workflow.md": "Git workflow and commit conventions",
        "security.md": "Security checks and practices",
        "testing.md": "Testing requirements (TDD, 80% coverage)",
        "architecture.md": "Architecture principles",
        "performance.md": "Performance and model selection",
        "agents.md": "Agent orchestration",
        "codemaps.md": "Codemap system",
        "hooks.md": "Hooks system",
    }

    # Sort rules: lang/template/platform first, then base rules alphabetically
    lang_rules = set(MODULAR_RULES.get("lang", {}).keys())
    template_rules = set(MODULAR_RULES.get("templates", {}).keys())
    platform_rules = set(MODULAR_RULES.get("platform", {}).keys())
    security_rules = set(MODULAR_RULES.get("security", {}).keys())
    modular_rules = lang_rules | template_rules | platform_rules | security_rules

    modular_first = sorted(r for r in deployed_rules if r in modular_rules)
    other_rules = sorted(r for r in deployed_rules if r not in modular_rules)
    ordered_rules = modular_first + other_rules

    rules_lines = []
    for rule in ordered_rules:
        desc = rule_descriptions.get(rule, rule.replace(".md", "").replace("-", " ").title())
        rules_lines.append(f"- `{rule}` — {desc}")
    rules_list = "\n".join(rules_lines) if rules_lines else "- (none deployed)"

    # Build environment commands
    env_lines = []
    for lang in sorted(selected_langs):
        if lang in ENVIRONMENT_SNIPPETS:
            snippets = ENVIRONMENT_SNIPPETS[lang]
            if "setup" in snippets:
                env_lines.append(f"{snippets['setup']}  # Setup")
            if "test" in snippets:
                env_lines.append(f"{snippets['test']}  # Tests")
    env_commands = "\n".join(env_lines) if env_lines else "# No language-specific commands configured"

    return CLAUDE_FOUNDRY_HEADER_TEMPLATE.format(
        marker_start=CLAUDE_FOUNDRY_MARKER_START,
        marker_end=CLAUDE_FOUNDRY_MARKER_END,
        rules_list=rules_list,
        env_commands=env_commands,
    )


def has_claude_foundry_header(content: str) -> bool:
    """Check if content has claude-foundry marker."""
    return CLAUDE_FOUNDRY_MARKER_START in content


def update_claude_foundry_header(content: str, new_header: str) -> str:
    """Replace existing claude-foundry header with new one."""
    start_idx = content.find(CLAUDE_FOUNDRY_MARKER_START)
    end_idx = content.find(CLAUDE_FOUNDRY_MARKER_END)

    if start_idx == -1 or end_idx == -1:
        return content

    # Include the end marker in the replacement
    end_idx += len(CLAUDE_FOUNDRY_MARKER_END)

    return content[:start_idx] + new_header.strip() + content[end_idx:]


def prepend_claude_foundry_header(content: str, header: str) -> str:
    """Prepend header to content with blank line separator."""
    return header + "\n" + content


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


# ── Detection ───────────────────────────────────────────────────────────


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
            try:
                text += p.read_text(encoding='utf-8', errors="ignore")
            except OSError:
                pass
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


# ── Private Sources ────────────────────────────────────────────────────

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
            print(f"  \u26a0 Private source missing: {source['path']} (skipped)")
            result.append(source)  # Keep in manifest so user can fix path
            continue
        clean_private_files(project, prefix)
        deployed = deploy_private_source(project, source_path, prefix, source)
        total = sum(len(v) for v in deployed.values())
        print(f"  \u2713 Private source re-applied: {prefix} ({total} files)")
        result.append({
            "path": str(source_path),
            "prefix": prefix,
            **deployed,
        })
    return result


# ── Generation ──────────────────────────────────────────────────────────


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


def generate_claude_md(
    project_name: str,
    deployed_rules: list[str],
    selected_langs: set[str],
) -> str:
    """Generate a new CLAUDE.md with claude-foundry header.

    Includes a user-editable Environment section above the marker for
    project-specific build/test/lint commands. This section is never
    overwritten by setup.py on subsequent runs.
    """
    header = generate_claude_foundry_header(deployed_rules, selected_langs)
    return f"""# {project_name}

## Environment

```bash
# Add your project's build, test, and lint commands here
```

{header}
"""


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
        src = REPO_ROOT / "rules" / rule
        if src.exists():
            shutil.copy2(src, rules_dir / rule)
            deployed.add(rule)

    # Modular rules (flatten into same dir; prefix with category only
    # on name collision with a base rule we just copied).
    for category, rules in modular.items():
        for rule in rules:
            src = REPO_ROOT / "rule-library" / category / rule
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
        src = REPO_ROOT / "skills" / skill
        dest = skills_dir / skill
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
    # Copy shared libraries (e.g., _lib/session-id.sh used by prj-* skills)
    lib_src = REPO_ROOT / "skills" / "_lib"
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
            src = REPO_ROOT / "hooks" / "library" / script
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
        print(f"  Migrated MCP servers from .claude.json → .mcp.json")


# ── Commands ────────────────────────────────────────────────────────────


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
    STEPS = (["base"] + modular_categories +
             ["hooks", "agents", "skills", "learned", "plugins", "mcp", "features"])
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
                            if name == "lang" and rule in detected_langs:
                                auto.add(i)
                            elif name == "templates" and rule in detected_templates:
                                auto.add(i)
                            elif name == "platform" and rule in detected_platform:
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
                            if any(r in sfd for r in ["react-app.md", "nodejs.md"]):
                                if "typescript" in af:
                                    auto.add(i)
                            if "desktop-gui-qt.md" in sfd:
                                if "python-qt" in af:
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
                    if interactive:
                        result = toggle_menu("Plugins", plugin_display, auto)
                    else:
                        result = auto
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
    selected_for_detection = selected_langs | selected_templates
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
                print(f"\n  WARNING: CLAUDE.md exists without claude-foundry marker.")
                print(f"  Force will merge the header into your existing CLAUDE.md.")
                if not confirm("  Proceed with force merge?", default=False):
                    print("  Aborted.")
                    return False
                force_merge = True
            else:
                # Non-interactive and no marker — skip entire project
                print(f"\n  CLAUDE.md exists without claude-foundry marker — skipping project")
                print(f"")
                print(f"  To add the marker, run setup.py init interactively:")
                print(f"    python3 <claude-foundry>/tools/setup.py init {project}")
                print(f"  Or use --force to merge the header (with confirmation).")
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
            print(f"  \u2713 Private source deployed: {prefix} ({total} files)")
            private_sources.append({"path": str(source_path), "prefix": prefix, **deployed})
    elif pending_private:
        # Deploy private sources collected during interactive step loop
        for ps in pending_private:
            clean_private_files(project, ps["prefix"])
            deployed = deploy_private_source(
                project, ps["source_path"], ps["prefix"], ps["selections"])
            total = sum(len(v) for v in deployed.values())
            print(f"  \u2713 Private source deployed: {ps['prefix']} ({total} files)")
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
            print(f"  Updated claude-foundry header in CLAUDE.md")
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
                print(f"  Replaced CLAUDE.md (original saved to CLAUDE.md.old)")
            else:  # M or anything else defaults to Merge
                # Save original and prepend header
                backup = project / "CLAUDE.md.old"
                backup.write_text(existing_content, encoding='utf-8')
                merged = prepend_claude_foundry_header(existing_content, header)
                claude_md.write_text(merged, encoding='utf-8')
                print(f"  Merged claude-foundry header into CLAUDE.md (original saved to CLAUDE.md.old)")
        elif force_merge:
            # Force merge — prepend header (confirmed earlier)
            backup = project / "CLAUDE.md.old"
            backup.write_text(existing_content, encoding='utf-8')
            merged = prepend_claude_foundry_header(existing_content, header)
            claude_md.write_text(merged, encoding='utf-8')
            print(f"  Force-merged claude-foundry header into CLAUDE.md (original saved to CLAUDE.md.old)")
        # Note: non-interactive + no marker without force case is handled earlier (skips entire project)
    else:
        claude_md.write_text(generate_claude_md(project_name, deployed_rules, selected_langs), encoding='utf-8')
        print(f"  Created CLAUDE.md")

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


_PAYLOAD_SKIP_NAMES = {
    ".git", "__pycache__", ".pytest_cache", ".venv", "venv",
    "node_modules", "out", ".vscode-test", "dist", "build",
    ".coverage", "results", ".claude",
    ".foundry", ".foundry.new", ".foundry.old", "foundry",
}


def _install_foundry_payload(
    project: Path, selected_features: list[str] | None = None,
) -> None:
    """Install foundry payload (tarball + setup.py) at <project>/.foundry/.

    Writes:
      <project>/.foundry/setup.py        — copy of the running script
      <project>/.foundry/foundry.tar.gz  — tarball of REPO_ROOT (or copy
                                           of the source tarball in
                                           tarball mode)

    Migrates: removes any legacy <project>/.claude/foundry/ tree and the
    obsolete .claude/.foundry.{new,old} staging dirs from older versions.

    Ensures <project>/.gitignore lists `.foundry/`.

    Skipped when REPO_ROOT lives inside the target project (running
    setup.py from a deployed payload against its own project — the
    payload is already canonical, no need to rewrite it).

    Args:
        project: Target project directory.
        selected_features: Keys from OPTIONAL_FEATURES the user opted
            into. Paths mapped in FEATURE_PATHS for features NOT in
            this list are excluded from the source-mode tarball build.
    """
    import atexit

    selected_features = selected_features or []
    project = project.resolve()

    legacy_root = project / ".claude" / "foundry"
    foundry_dir = project / ".foundry"

    # Detect the migration boundary case: an old update-foundry.sh
    # extracted the new release into <project>/.claude/foundry/ and
    # invoked us from there. We can't delete the dir we're running from
    # mid-run (Linux survives via inode refcounting but it's racy;
    # Windows fails silently). Defer the legacy cleanup to atexit so the
    # dir is wiped only after Python exits.
    running_from_legacy = False
    if legacy_root.is_dir():
        try:
            REPO_ROOT.relative_to(legacy_root)
            running_from_legacy = True
        except ValueError:
            pass
        if not running_from_legacy:
            shutil.rmtree(legacy_root, ignore_errors=True)
            print(f"  Removed legacy foundry copy: {legacy_root}")

    for stale in (
        project / ".claude" / ".foundry.new",
        project / ".claude" / ".foundry.old",
        project / ".claude" / ".foundry-release.tar.gz",
    ):
        if stale.exists():
            if stale.is_dir():
                shutil.rmtree(stale, ignore_errors=True)
            else:
                stale.unlink()

    # Skip when REPO_ROOT is already canonical (deployed setup.py running
    # against its own project — payload is in place, nothing to write).
    try:
        REPO_ROOT.relative_to(foundry_dir)
        return
    except ValueError:
        pass

    # Skip when running setup.py from the foundry repo against itself
    # (no point tarballing the source we're sitting on into ./foundry/
    # inside it). The legacy-running case is allowed through — we still
    # need to install the new payload in that one.
    if not running_from_legacy:
        try:
            REPO_ROOT.relative_to(project)
            return
        except ValueError:
            pass

    foundry_dir.mkdir(parents=True, exist_ok=True)

    # Tarball: in tarball mode we already have the canonical artifact next
    # to the running setup.py — just make sure it lives at the canonical
    # path. In source mode, build a fresh tarball from REPO_ROOT.
    target_tarball = foundry_dir / "foundry.tar.gz"
    if _TARBALL_MODE and _PAYLOAD_TARBALL is not None and _PAYLOAD_TARBALL.is_file():
        if _PAYLOAD_TARBALL.resolve() != target_tarball.resolve():
            shutil.copy2(_PAYLOAD_TARBALL, target_tarball)
    else:
        _build_foundry_tarball(REPO_ROOT, target_tarball, selected_features)

    # setup.py copy: always refresh from REPO_ROOT so it matches the tarball
    src_setup = REPO_ROOT / "tools" / "setup.py"
    dst_setup = foundry_dir / "setup.py"
    shutil.copy2(src_setup, dst_setup)

    _ensure_gitignore_entry(project / ".gitignore", ".foundry/")
    # Delegate runtime state lives at <project>/.delegate/ when the
    # minimax-delegate feature is enabled — gitignore it too.
    if "minimax-delegate" in selected_features:
        _ensure_gitignore_entry(project / ".gitignore", ".delegate/")

    # If we were invoked from inside the legacy .claude/foundry/ tree,
    # defer its removal until after Python exits — we can't safely rmtree
    # the dir we're executing from while it's still in use.
    if running_from_legacy:
        atexit.register(shutil.rmtree, str(legacy_root), True)
        print(f"  Legacy {legacy_root} will be removed on exit")

    print(f"  Foundry payload installed at: {foundry_dir}")
    print(f"    Manual re-init: python3 {dst_setup} init {project}")


def _build_foundry_tarball(
    src_root: Path,
    out_path: Path,
    selected_features: list[str] | None = None,
) -> None:
    """Build a gzipped tarball of `src_root` at `out_path`.

    Excludes caches/build artifacts, the maintainer's local `.claude/`
    dev install, and any feature-gated paths the user didn't opt into.
    The tarball uses a top-level wrapper directory `claude-foundry-<ver>/`
    matching the GitHub release tarball convention.

    Writes to a `.tmp` sibling first and atomically renames into place
    so a crash mid-build never leaves a partial tarball.
    """
    import tarfile

    selected_features = selected_features or []
    excluded_abs: set[str] = set()
    for key, paths in FEATURE_PATHS.items():
        if key in selected_features:
            continue
        for rel in paths:
            excluded_abs.add(str((src_root / rel).resolve()))

    arc_root = f"claude-foundry-{read_version()}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    try:
        with tarfile.open(tmp_path, "w:gz") as tf:
            for root, dirs, files in os.walk(src_root, topdown=True):
                root_path = Path(root)
                # Prune subdirs in-place to skip caches and feature-gated paths
                kept_dirs = []
                for d in dirs:
                    if d in _PAYLOAD_SKIP_NAMES:
                        continue
                    if str((root_path / d).resolve()) in excluded_abs:
                        continue
                    kept_dirs.append(d)
                dirs[:] = kept_dirs

                for fname in files:
                    if fname in _PAYLOAD_SKIP_NAMES:
                        continue
                    fpath = root_path / fname
                    if str(fpath.resolve()) in excluded_abs:
                        continue
                    arcname = f"{arc_root}/{fpath.relative_to(src_root).as_posix()}"
                    tf.add(fpath, arcname=arcname, recursive=False)
        tmp_path.replace(out_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


_GITIGNORE_HEADER = "# claude-foundry payload"


def _ensure_gitignore_entry(gitignore: Path, entry: str) -> None:
    """Append `entry` to `gitignore` if not already present.

    Matches both `.foundry/` and `.foundry` style entries to avoid duplicates.
    The `# claude-foundry payload` comment is emitted only on the first
    foundry entry; subsequent entries append directly to the same block.
    """
    needle = entry.rstrip("/")
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    for line in existing.splitlines():
        if line.strip().rstrip("/") == needle:
            return
    if existing and not existing.endswith("\n"):
        existing += "\n"
    if _GITIGNORE_HEADER in existing:
        new_content = existing + entry + "\n"
    else:
        new_content = existing + "\n" + _GITIGNORE_HEADER + "\n" + entry + "\n"
    gitignore.write_text(new_content, encoding="utf-8")


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


# ── Main ────────────────────────────────────────────────────────────────


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
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
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
