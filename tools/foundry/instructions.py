"""Instruction-file helpers: the marker-wrapped foundry block, and moving a
project's CLAUDE.md into AGENTS.md.

Every target CLI — Claude Code included — reads AGENTS.md, so that is the
one instructions file the foundry writes. Claude Code reads AGENTS.md only
while no CLAUDE.md exists (in the project or any directory above it), so a
CLAUDE.md is folded into AGENTS.md rather than kept next to it.
"""

from __future__ import annotations

from pathlib import Path

from .paths import AGENT_FOUNDRY_MARKER_END, AGENT_FOUNDRY_MARKER_START
from .registry import ENVIRONMENT_SNIPPETS, RULE_DESCRIPTIONS


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


def project_text(content: str) -> str:
    """The project's own part of an instructions file: everything outside
    the foundry block, trimmed."""
    before, _, after = update_agent_foundry_header(content, "\0").partition("\0")
    return "\n\n".join(part.strip() for part in (before, after) if part.strip())


def merge_project_text(agents_md: str, moved: str, project_name: str) -> str:
    """Add ``moved`` (CLAUDE.md's project text) to AGENTS.md's content.

    The result carries an empty foundry block right after the moved text,
    for the caller to fill — so the standards follow the project's own
    instructions, as they did in CLAUDE.md. An AGENTS.md holding only the
    stub title is replaced; otherwise its own content stays, and a title
    both files share appears once.
    """
    placeholder = f"{AGENT_FOUNDRY_MARKER_START}\n{AGENT_FOUNDRY_MARKER_END}"
    own = project_text(agents_md)
    if own in ("", f"# {project_name}"):
        return f"{moved}\n\n{placeholder}\n"
    title, _, rest = moved.partition("\n")
    if title.startswith("# ") and title.strip() == own.partition("\n")[0].strip():
        moved = rest.strip()
    if has_agent_foundry_header(agents_md):
        return update_agent_foundry_header(agents_md, f"{moved}\n\n{placeholder}")
    return f"{agents_md.rstrip()}\n\n{moved}\n\n{placeholder}\n"


# Instruction files that make Claude Code skip AGENTS.md when one exists in
# the project or any directory above it. The user-level
# ~/.claude/CLAUDE.md doesn't count; it loads alongside AGENTS.md.
_CLAUDE_MD_NAMES = ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md")


def claude_md_blockers(project: Path) -> list[Path]:
    """Files that stop Claude Code from reading the project's AGENTS.md."""
    user_memory = (Path.home() / ".claude" / "CLAUDE.md").resolve()
    return [path for directory in (project, *project.parents)
            for path in (directory / name for name in _CLAUDE_MD_NAMES)
            if path.is_file() and path.resolve() != user_memory]
