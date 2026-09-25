"""CLAUDE.md header generation and merge helpers."""

from __future__ import annotations

from .paths import AGENT_FOUNDRY_MARKER_END, AGENT_FOUNDRY_MARKER_START
from .registry import (
    AGENT_FOUNDRY_HEADER_TEMPLATE,
    ENVIRONMENT_SNIPPETS,
    MODULAR_RULES,
    RULE_DESCRIPTIONS,
)


def rule_description(rule: str) -> str:
    """One-line description for a rule filename."""
    return RULE_DESCRIPTIONS.get(rule, rule.replace(".md", "").replace("-", " ").title())


def render_env_commands(selected_langs: set[str]) -> str:
    """Setup/test commands for languages with a near-universal toolchain."""
    env_lines = []
    for lang in sorted(selected_langs):
        snippets = ENVIRONMENT_SNIPPETS.get(lang, {})
        if "setup" in snippets:
            env_lines.append(f"{snippets['setup']}  # Setup")
        if "test" in snippets:
            env_lines.append(f"{snippets['test']}  # Tests")
    return "\n".join(env_lines) if env_lines else "# No language-specific commands configured"


def generate_agent_foundry_header(
    deployed_rules: list[str],
    selected_langs: set[str],
) -> str:
    """Generate the agent-foundry header for CLAUDE.md."""
    # Sort rules: lang/template/platform first, then base rules alphabetically
    lang_rules = set(MODULAR_RULES.get("lang", {}).keys())
    template_rules = set(MODULAR_RULES.get("templates", {}).keys())
    platform_rules = set(MODULAR_RULES.get("platform", {}).keys())
    security_rules = set(MODULAR_RULES.get("security", {}).keys())
    modular_rules = lang_rules | template_rules | platform_rules | security_rules

    modular_first = sorted(r for r in deployed_rules if r in modular_rules)
    other_rules = sorted(r for r in deployed_rules if r not in modular_rules)
    ordered_rules = modular_first + other_rules

    rules_lines = [f"- `{rule}` — {rule_description(rule)}" for rule in ordered_rules]
    rules_list = "\n".join(rules_lines) if rules_lines else "- (none deployed)"

    return AGENT_FOUNDRY_HEADER_TEMPLATE.format(
        marker_start=AGENT_FOUNDRY_MARKER_START,
        marker_end=AGENT_FOUNDRY_MARKER_END,
        rules_list=rules_list,
        env_commands=render_env_commands(selected_langs),
    )


# Current markers first, then the ones releases wrote before the
# claude-foundry → agent-foundry rename. A legacy-marked header is still
# ours: updating it rewrites the block with the current markers.
_HEADER_MARKERS = (
    (AGENT_FOUNDRY_MARKER_START, AGENT_FOUNDRY_MARKER_END),
    ("<!-- claude-foundry -->", "<!-- /claude-foundry -->"),
)


def has_agent_foundry_header(content: str) -> bool:
    """Check if content has an agent-foundry marker (current or legacy)."""
    return any(start in content for start, _ in _HEADER_MARKERS)


def update_agent_foundry_header(content: str, new_header: str) -> str:
    """Replace existing agent-foundry header (current or legacy) with new one."""
    for marker_start, marker_end in _HEADER_MARKERS:
        start_idx = content.find(marker_start)
        end_idx = content.find(marker_end)
        if start_idx != -1 and end_idx != -1:
            # Include the end marker in the replacement
            end_idx += len(marker_end)
            return content[:start_idx] + new_header.strip() + content[end_idx:]
    return content


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
