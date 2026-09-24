"""CLI adapter registry.

Maps a CLI id to its adapter class. The orchestrator looks adapters up here
by the ids stored in the manifest's ``clis`` list.
"""

from __future__ import annotations

from .base import CliAdapter, DeployContext, DeployResult, Selections
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .copilot import CopilotAdapter

ADAPTERS: dict[str, type[CliAdapter]] = {
    ClaudeAdapter.id: ClaudeAdapter,
    CopilotAdapter.id: CopilotAdapter,
    CodexAdapter.id: CodexAdapter,
}

# Default target when a project/manifest predates multi-CLI support.
DEFAULT_CLIS = [ClaudeAdapter.id]

__all__ = [
    "ADAPTERS",
    "DEFAULT_CLIS",
    "ClaudeAdapter",
    "CliAdapter",
    "CodexAdapter",
    "CopilotAdapter",
    "DeployContext",
    "DeployResult",
    "Selections",
]
