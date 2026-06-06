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


@dataclass
class DeployResult:
    """What an adapter reports back to the orchestrator."""

    ok: bool = True
    private_sources: list[dict] = field(default_factory=list)


class CliAdapter(ABC):
    """Base class for a coding-agent CLI deployment target."""

    id: str = ""
    display_name: str = ""

    def config_root(self, project: Path) -> Path:
        """Directory this CLI reads its config from, inside the project."""
        return project

    @abstractmethod
    def supported_artifacts(self) -> set[str]:
        """Artifact types this CLI can consume.

        Possible values: ``rules``, ``mcp``, ``agents``, ``skills``,
        ``commands``, ``hooks``. Types a CLI cannot consume are reported as
        not-applicable by the orchestrator rather than silently dropped.
        """

    @abstractmethod
    def deploy(self, project: Path, sel: Selections, ctx: DeployContext) -> DeployResult:
        """Render the selections into this CLI's layout. Return ok=False to
        abort the whole init (e.g. user declined to touch an existing
        instructions file)."""
