"""GitHub Copilot CLI adapter.

Copilot CLI reads only files other CLIs read too, so everything it gets is a
shared output written once by the orchestrator (see foundry/shared.py):
- coding-standard rules → the AGENTS.md block (+ .agents/rules/ overflow)
- MCP servers → the workspace .mcp.json (verified against Copilot CLI 1.0.58)
- portable reasoning skills → .agents/skills/ (Copilot CLI 1.0.69 loads
  .github/skills/, .agents/skills/ and .claude/skills/ as project skills)

Claude-only artifact types — subagents, slash-commands, PostToolUse hooks, and
Claude-coupled skills (prj-*/review-process/etc.) — are not deployed; the
orchestrator reports them as skipped.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import (
    AGENTS_MD,
    AGENTS_SKILLS,
    MCP_JSON,
    CliAdapter,
    DeployContext,
    DeployResult,
    Selections,
)

# Before the shared .agents/skills/ root, foundry deployed Copilot skills to
# .github/skills/ — only these four ever went there.
_LEGACY_SKILLS_DIR = Path(".github") / "skills"
_LEGACY_SKILLS = ("megamind-adversarial", "megamind-creative", "megamind-deep",
                  "megamind-financial")


def _remove_legacy_skills(project: Path) -> None:
    """Remove foundry copies from .github/skills/; they now live in .agents/skills/."""
    legacy_root = project / _LEGACY_SKILLS_DIR
    for name in _LEGACY_SKILLS:
        legacy = legacy_root / name
        skill_md = legacy / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8", errors="replace") if skill_md.is_file() else ""
        if legacy.is_dir() and f"\nname: {name}\n" in text.split("\n---", 1)[0] + "\n":
            shutil.rmtree(legacy)
            print(f"  Removed legacy foundry copy {_LEGACY_SKILLS_DIR.as_posix()}/{name}/ "
                  "(now in .agents/skills/)")
    if legacy_root.is_dir() and not any(legacy_root.iterdir()):
        legacy_root.rmdir()


class CopilotAdapter(CliAdapter):
    id = "copilot"
    display_name = "GitHub Copilot CLI"
    shared_outputs = frozenset({AGENTS_MD, AGENTS_SKILLS, MCP_JSON})
    # Copilot CLI 1.0.69 loads .claude/skills/ and .claude/commands/*.md as
    # project skills (deduped by name against .agents/skills/).
    reads_claude_skills = True

    def config_root(self, project: Path) -> Path:
        return project

    def supported_artifacts(self) -> set[str]:
        return {"rules", "mcp", "skills"}

    def undeploy(self, project: Path, ctx: DeployContext) -> None:
        pass  # everything Copilot gets is a shared output, removed with the last reader

    def deploy(self, project: Path, sel: Selections, ctx: DeployContext) -> DeployResult:
        _remove_legacy_skills(project)
        return DeployResult(ok=True)
