"""Static data tables: rules, hooks, skills, plugins, templates.

This is a leaf module — it holds only module-level constants and lookup
tables, with no behavior. The environment snippets rendered into AGENTS.md
live here too since they are static data.
"""

from __future__ import annotations

# Only languages with near-universal toolchains get default commands.
# Languages with fragmented build systems (C, C++, Node.js, React) are
# omitted — users add their own commands to AGENTS.md, outside the
# agent-foundry block.
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

# Base rules that describe Claude Code-only machinery (the Task tool and the
# foundry subagent roster, settings.json hooks, Claude model tiers). They
# deploy to .claude/rules/ (which Claude Code loads alongside AGENTS.md) and
# are never rendered into the shared AGENTS.md, where they would mislead
# Copilot, Codex, and Antigravity.
CLAUDE_ONLY_RULES: set[str] = {"agents.md", "hooks.md", "performance.md"}

# One-line descriptions shown next to each rule in the AGENTS.md pointer
# list and in Antigravity rule frontmatter. Rules missing here get a title-cased name.
RULE_DESCRIPTIONS: dict[str, str] = {
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

# Names the foundry once shipped but no longer does. The deploy prunes
# only ever delete names they can prove are foundry-owned — the current
# catalog or these sets — never content the foundry didn't ship. So when
# a skill/command/agent is renamed or removed, its old name must be
# listed here to keep being cleaned out of projects. Rules don't need a
# set: MANIFEST_MIGRATION below already records retired rule names.
RETIRED_SKILLS: set[str] = set()
RETIRED_COMMANDS: set[str] = {
    "recall.md",  # became the learn-recall skill
}
RETIRED_AGENTS: set[str] = set()

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
    "delegate", "review-process",
    "update-foundry", "learn", "learn-recall", "snapshot-list",
    "private-list", "private-remove",
    "prj-new", "prj-list", "prj-pause", "prj-resume", "prj-done", "prj-delete",
    "copilot-cli", "codex-cli", "agy-cli",
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

# Skills portable to every non-Claude CLI. They deploy once to the shared
# .agents/skills/ root, which Copilot CLI (1.0.69), Codex (0.156) and
# Antigravity (1.2.10) all load natively — so "portable" means safe on any
# of them, not just one. Deploying adapts them (see shared.py): Claude-only
# frontmatter is dropped, .claude/skills/ paths and Skill(x) calls are
# rewritten, and files over Codex's 8 KB skill limit are split. Excluded:
# skills tied to Claude-only state (prj-*/snapshot-list/learn* → Claude
# session ids and .claude/ layouts, private-* → Claude-only private
# sources, review-process → Claude reviewer agents and prompts).
PORTABLE_SKILLS: set[str] = {
    "megamind-deep", "megamind-creative", "megamind-adversarial", "megamind-financial",
    "clickhouse-io", "gui-threading", "python-qt-gui", "writer", "humanizer",
    "update-foundry", "copilot-cli", "codex-cli", "agy-cli", "delegate",
}

# Claude slash commands that work on any CLI. Copilot, Codex and Antigravity
# have no command files (Codex removed custom prompts in 0.117), so these are
# converted to skills in .agents/skills/ (sub-commands only with their
# skill). The snapshot commands keep state in .claude/ and stay Claude-only.
PORTABLE_COMMANDS: set[str] = {
    "update-codemaps.md", "update-foundry-check.md", "update-foundry-interactive.md",
}

# Skills that are never shown in the interactive skill menu. None today —
# kept as an explicit empty set so the menu-build logic stays uniform.
HIDDEN_SKILLS: set[str] = set()

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
