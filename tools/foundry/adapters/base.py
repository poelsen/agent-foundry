"""CLI adapter interface and the data bundles passed to adapters.

An adapter encapsulates everything specific to one coding-agent CLI: where
its config lives, which artifact types it can consume, and how the selected
foundry artifacts are rendered into that CLI's native layout. The
orchestrator selects artifacts once, then asks each chosen adapter to deploy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..registry import CLAUDE_ONLY_RULES, PORTABLE_SKILLS

# Shared outputs: project files more than one CLI reads. An adapter lists the
# ones its CLI consumes in ``shared_outputs``; the orchestrator writes each
# once per run for all selected CLIs (see foundry/shared.py) instead of
# letting every adapter render the same file.
AGENTS_MD = "agents_md"          # AGENTS.md block (+ .agents/rules/ overflow)
AGENTS_SKILLS = "agents_skills"  # portable skills in .agents/skills/
MCP_JSON = "mcp_json"            # MCP servers in the workspace .mcp.json

# Selection fields reported by CliAdapter.skipped(), as (artifact, attribute).
_REPORTED_SELECTIONS = (
    ("rules", "deployed_rules"),
    ("agents", "agents"),
    ("skills", "skills"),
    ("learned", "learned"),
    ("hooks", "hooks"),
    ("plugins", "plugins"),
    ("mcp", "mcp_servers"),
)


@dataclass
class Selections:
    """CLI-agnostic result of the selection phase — what to deploy."""

    base: list[str]
    modular: dict[str, list[str]]
    agents: list[str]
    skills: list[str]
    learned: list[str]
    hooks: list[str]
    plugins: list[str]
    mcp_servers: list[str]
    features: list[str]
    langs: set[str]
    project_name: str
    version: str

    @property
    def deployed_rules(self) -> list[str]:
        """Flat list of every selected rule (base + modular), for headers."""
        rules = self.base.copy()
        for group in self.modular.values():
            rules.extend(group)
        return rules


@dataclass
class DeployContext:
    """Per-run deployment context shared across adapters."""

    interactive: bool
    force: bool
    private_prefixes: list[str]
    pending_private: list[dict]
    existing_private: list[dict]
    cli_private_sources: list[tuple[str, str]]
    # MCP renderings the foundry deployed, per config file, from the last
    # run's manifest; writers update it and the orchestrator saves it back.
    mcp_state: dict = field(default_factory=dict)


@dataclass
class DeployResult:
    """What an adapter reports back to the orchestrator."""

    ok: bool = True
    private_sources: list[dict] = field(default_factory=list)


@dataclass
class Skipped:
    """Selected items one CLI will not receive."""

    artifact: str
    items: list[str]
    # True when the CLI supports the artifact type but these particular
    # items are Claude-only; False when it can't consume the type at all.
    claude_only: bool = False


class CliAdapter(ABC):
    """Base class for a coding-agent CLI deployment target."""

    id: str = ""
    display_name: str = ""
    shared_outputs: frozenset[str] = frozenset()
    # True if this CLI also loads Claude Code's .claude/skills/ (and
    # commands) on its own, so Claude-only skills reach it anyway whenever
    # Claude Code is a target too.
    reads_claude_skills: bool = False
    # Bytes of AGENTS.md this CLI reads before silently truncating, if known.
    agents_md_limit: int | None = None

    def config_root(self, project: Path) -> Path:
        """Directory this CLI reads its config from, inside the project."""
        return project

    @abstractmethod
    def supported_artifacts(self) -> set[str]:
        """Artifact types this CLI can consume.

        Possible values: ``rules``, ``mcp``, ``agents``, ``skills``,
        ``commands``, ``hooks``, ``plugins``, ``learned``,
        ``private-sources``. The orchestrator only offers selection menus
        for types some selected CLI consumes, and reports selected items a
        CLI can't use (see :meth:`skipped`) rather than dropping them
        silently.
        """

    def skipped(self, sel: Selections) -> list[Skipped]:
        """Selected items this CLI will not receive, for the post-run report."""
        supported = self.supported_artifacts()
        report: list[Skipped] = []
        for artifact, attr in _REPORTED_SELECTIONS:
            items = list(getattr(sel, attr))
            if not items:
                continue
            if artifact not in supported:
                report.append(Skipped(artifact, items))
            elif artifact == "rules" and AGENTS_MD in self.shared_outputs:
                claude_only = [r for r in items if r in CLAUDE_ONLY_RULES]
                if claude_only:
                    report.append(Skipped(artifact, claude_only, claude_only=True))
            elif artifact == "skills" and AGENTS_SKILLS in self.shared_outputs:
                claude_only = [s for s in items if s not in PORTABLE_SKILLS]
                if claude_only:
                    report.append(Skipped(artifact, claude_only, claude_only=True))
        return report

    def undeploy(self, project: Path, ctx: DeployContext) -> None:
        """Remove what this CLI's adapter deployed, after the user dropped it
        as a target. Default: leave it in place and say so."""
        print(f"  {self.display_name} is no longer a target; its config was left in place "
              f"— delete {self.config_root(project).name}/ yourself if unwanted")

    @abstractmethod
    def deploy(self, project: Path, sel: Selections, ctx: DeployContext) -> DeployResult:
        """Render the selections into this CLI's layout. Return ok=False to
        abort the whole init (e.g. user declined to touch an existing
        instructions file)."""
