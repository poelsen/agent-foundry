"""Static data tables: rules, hooks, skills, plugins, features, templates.

This is a leaf module — it holds only module-level constants and lookup
tables, with no behavior. The CLAUDE.md header template and environment
snippets live here too since they are static data.
"""

from __future__ import annotations

AGENT_FOUNDRY_HEADER_TEMPLATE = """{marker_start}
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
# above the agent-foundry marker.
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

SKILLS = [
    "clickhouse-io", "gui-threading", "python-qt-gui",
    "megamind-deep", "megamind-creative", "megamind-adversarial", "megamind-financial",
    "minimax-multimodal", "delegate", "review-process",
    "update-foundry", "learn", "learn-recall", "snapshot-list",
    "private-list", "private-remove",
    "prj-new", "prj-list", "prj-pause", "prj-resume", "prj-done", "prj-delete",
    "copilot-cli",
    "writer", "humanizer",
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
    # writer drafts in the user's voice, then invokes humanizer via Skill(humanizer)
    # for the reactive anti-AI audit. Grouped so the pair always deploys together —
    # the invocation only resolves if humanizer is present in the target project.
    "Writing": [
        "writer", "humanizer",
    ],
}

# Skills portable to non-Claude CLIs that natively read SKILL.md (verified
# against GitHub Copilot CLI 1.0.58, which loads skills from .github/skills/).
# Limited to pure reasoning workflows — skills that wire into Claude-only
# machinery (prj-*/snapshot/update-foundry/learn → .claude/, slash-commands,
# session ids; review-process → Claude reviewer agents) are intentionally
# excluded.
COPILOT_PORTABLE_SKILLS: set[str] = {
    "megamind-deep", "megamind-creative", "megamind-adversarial", "megamind-financial",
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
        "cli/claude/commands/delegate.md",
        "cli/claude/skills/delegate",
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
