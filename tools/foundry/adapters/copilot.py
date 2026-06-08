"""GitHub Copilot CLI adapter — emits AGENTS.md + MCP + skills.

Consumes the cross-CLI-portable artifacts:
- coding-standard rules → embedded into a self-contained AGENTS.md
- MCP servers → the cross-vendor .mcp.json (Copilot reads it as a workspace source)
- portable reasoning skills → .github/skills/<name>/ (Copilot CLI 1.0.58 loads
  SKILL.md skills natively; verified empirically)

Claude-only artifact types — subagents, slash-commands, PostToolUse hooks, and
Claude-coupled skills (prj-*/review-process/etc.) — have no Copilot equivalent
and are skipped.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..deploy import write_mcp_servers
from ..instructions import (
    has_agent_foundry_header,
    prepend_agent_foundry_header,
    update_agent_foundry_header,
)
from ..paths import (
    AGENT_FOUNDRY_MARKER_END,
    AGENT_FOUNDRY_MARKER_START,
    REPO_ROOT,
)
from ..registry import COPILOT_PORTABLE_SKILLS, ENVIRONMENT_SNIPPETS
from .base import CliAdapter, DeployContext, DeployResult, Selections

# Copilot CLI skill frontmatter fields. `model` (Claude-style) is not among
# them, so it is stripped when deploying a foundry skill to Copilot.
_UNSUPPORTED_SKILL_FRONTMATTER = ("model",)


def _rule_source(rule: str, modular: dict[str, list[str]]) -> Path | None:
    """Resolve a deployed rule name to its source file under common/."""
    for category, rules in modular.items():
        if rule in rules:
            return REPO_ROOT / "common" / "rule-library" / category / rule
    base = REPO_ROOT / "common" / "rules" / rule
    return base if base.exists() else None


def _env_block(langs: set[str]) -> str:
    lines: list[str] = []
    for lang in sorted(langs):
        snippets = ENVIRONMENT_SNIPPETS.get(lang, {})
        if "setup" in snippets:
            lines.append(f"{snippets['setup']}  # Setup")
        if "test" in snippets:
            lines.append(f"{snippets['test']}  # Tests")
    return "\n".join(lines) if lines else "# No language-specific commands configured"


def render_agents_header(sel: Selections) -> str:
    """Build the marker-wrapped agent-foundry block embedding rule bodies."""
    sections = [AGENT_FOUNDRY_MARKER_START,
                "## Coding Standards (agent-foundry)",
                "",
                "These standards are managed by agent-foundry and apply to any "
                "CLI that reads `AGENTS.md`.",
                "",
                "### Environment",
                "",
                "```bash",
                _env_block(sel.langs),
                "```",
                ""]
    for rule in sel.deployed_rules:
        src = _rule_source(rule, sel.modular)
        if src is None:
            continue
        body = src.read_text(encoding="utf-8").strip()
        sections.append(f"<!-- rule: {rule} -->")
        sections.append(body)
        sections.append("")
    sections.append(AGENT_FOUNDRY_MARKER_END)
    return "\n".join(sections)


def _sanitize_skill_frontmatter(skill_md: Path) -> None:
    """Drop frontmatter keys Copilot CLI doesn't recognize (e.g. `model`)."""
    if not skill_md.exists():
        return
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return
    end = text.find("\n---", 3)
    if end == -1:
        return
    fm, rest = text[:end], text[end:]
    drop = re.compile(rf"^\s*({'|'.join(_UNSUPPORTED_SKILL_FRONTMATTER)})\s*:.*$\n?",
                      re.MULTILINE)
    skill_md.write_text(drop.sub("", fm) + rest, encoding="utf-8")


class CopilotAdapter(CliAdapter):
    id = "copilot"
    display_name = "GitHub Copilot CLI"

    def config_root(self, project: Path) -> Path:
        return project

    def supported_artifacts(self) -> set[str]:
        return {"rules", "mcp", "skills"}

    def _deploy_skills(self, project: Path, sel: Selections) -> None:
        """Deploy portable reasoning skills to .github/skills/ (Copilot's
        native skill root). Only COPILOT_PORTABLE_SKILLS are eligible; the
        managed set is reconciled each run so deselected skills are removed."""
        skills_root = project / ".github" / "skills"
        for name in sorted(COPILOT_PORTABLE_SKILLS):
            dest = skills_root / name
            if name in sel.skills:
                src = REPO_ROOT / "cli" / "claude" / "skills" / name
                if not src.is_dir():
                    continue
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
                _sanitize_skill_frontmatter(dest / "SKILL.md")
                print(f"  Deployed skill → .github/skills/{name}/")
            elif dest.exists():
                # No longer selected — remove the foundry-managed copy.
                shutil.rmtree(dest)

    def deploy(self, project: Path, sel: Selections, ctx: DeployContext) -> DeployResult:
        agents_md = project / "AGENTS.md"
        header = render_agents_header(sel)

        if agents_md.exists():
            existing = agents_md.read_text(encoding="utf-8")
            if has_agent_foundry_header(existing):
                agents_md.write_text(
                    update_agent_foundry_header(existing, header), encoding="utf-8")
                print("  Updated agent-foundry block in AGENTS.md")
            else:
                backup = project / "AGENTS.md.old"
                backup.write_text(existing, encoding="utf-8")
                agents_md.write_text(
                    prepend_agent_foundry_header(header, existing), encoding="utf-8")
                print("  Merged agent-foundry block into AGENTS.md (original saved to AGENTS.md.old)")
        else:
            agents_md.write_text(f"# {sel.project_name}\n\n{header}\n", encoding="utf-8")
            print("  Created AGENTS.md")

        # MCP servers via project .mcp.json. Verified against Copilot CLI
        # 1.0.58: `copilot mcp` loads servers from the workspace .mcp.json
        # (alongside the user-level ~/.copilot/mcp-config.json), so this is
        # Copilot's native per-project source — same file Claude Code reads.
        if sel.mcp_servers:
            write_mcp_servers(project, sel.mcp_servers)

        # Portable reasoning skills → .github/skills/ (Copilot's native root).
        self._deploy_skills(project, sel)

        return DeployResult(ok=True)
