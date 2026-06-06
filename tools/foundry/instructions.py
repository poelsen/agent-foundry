"""CLAUDE.md header generation and merge helpers."""

from __future__ import annotations

from .paths import AGENT_FOUNDRY_MARKER_END, AGENT_FOUNDRY_MARKER_START
from .registry import (
    AGENT_FOUNDRY_HEADER_TEMPLATE,
    ENVIRONMENT_SNIPPETS,
    MODULAR_RULES,
)


def generate_agent_foundry_header(
    deployed_rules: list[str],
    selected_langs: set[str],
) -> str:
    """Generate the agent-foundry header for CLAUDE.md."""
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

    return AGENT_FOUNDRY_HEADER_TEMPLATE.format(
        marker_start=AGENT_FOUNDRY_MARKER_START,
        marker_end=AGENT_FOUNDRY_MARKER_END,
        rules_list=rules_list,
        env_commands=env_commands,
    )


def has_agent_foundry_header(content: str) -> bool:
    """Check if content has agent-foundry marker."""
    return AGENT_FOUNDRY_MARKER_START in content


def update_agent_foundry_header(content: str, new_header: str) -> str:
    """Replace existing agent-foundry header with new one."""
    start_idx = content.find(AGENT_FOUNDRY_MARKER_START)
    end_idx = content.find(AGENT_FOUNDRY_MARKER_END)

    if start_idx == -1 or end_idx == -1:
        return content

    # Include the end marker in the replacement
    end_idx += len(AGENT_FOUNDRY_MARKER_END)

    return content[:start_idx] + new_header.strip() + content[end_idx:]


def prepend_agent_foundry_header(content: str, header: str) -> str:
    """Prepend header to content with blank line separator."""
    return header + "\n" + content


def generate_claude_md(
    project_name: str,
    deployed_rules: list[str],
    selected_langs: set[str],
) -> str:
    """Generate a new CLAUDE.md with agent-foundry header.

    Includes a user-editable Environment section above the marker for
    project-specific build/test/lint commands. This section is never
    overwritten by setup.py on subsequent runs.
    """
    header = generate_agent_foundry_header(deployed_rules, selected_langs)
    return f"""# {project_name}

## Environment

```bash
# Add your project's build, test, and lint commands here
```

{header}
"""
