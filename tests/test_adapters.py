"""Tests for the multi-CLI adapter layer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from foundry.adapters import (
    ADAPTERS,
    DEFAULT_CLIS,
    ClaudeAdapter,
    CopilotAdapter,
    DeployContext,
    Selections,
)
from foundry.manifest import migrate_manifest
from foundry.orchestrator import _select_clis, cmd_init


def _selections(**overrides) -> Selections:
    base = {
        "base": ["coding-style.md"],
        "modular": {"lang": ["python.md"]},
        "agents": [],
        "skills": [],
        "learned": [],
        "hooks": [],
        "plugins": [],
        "mcp_servers": [],
        "features": [],
        "langs": {"python.md"},
        "project_name": "demo",
        "version": "9999.99.99",
    }
    base.update(overrides)
    return Selections(**base)


def _ctx(**overrides) -> DeployContext:
    base = {
        "interactive": False,
        "force": False,
        "private_prefixes": [],
        "pending_private": [],
        "existing_private": [],
        "cli_private_sources": [],
    }
    base.update(overrides)
    return DeployContext(**base)


# ── Registry ──


def test_registry_has_claude_and_copilot():
    assert set(ADAPTERS) == {"claude", "copilot"}
    assert DEFAULT_CLIS == ["claude"]


def test_supported_artifacts_differ():
    assert "agents" in ClaudeAdapter().supported_artifacts()
    # Copilot has no subagent/skill/hook equivalent
    assert CopilotAdapter().supported_artifacts() == {"rules", "mcp"}
    assert "agents" not in CopilotAdapter().supported_artifacts()


# ── _select_clis ──


def test_select_clis_non_interactive_returns_saved():
    assert _select_clis(["copilot"], interactive=False) == ["copilot"]


def test_select_clis_filters_unknown_and_falls_back():
    assert _select_clis(["bogus"], interactive=False) == ["claude"]
    assert _select_clis([], interactive=False) == ["claude"]


# ── manifest migration ──


def test_migrate_backfills_clis():
    assert migrate_manifest({"version": "1.0"})["clis"] == ["claude"]


def test_migrate_preserves_explicit_clis():
    m = migrate_manifest({"version": "1.0", "clis": ["claude", "copilot"]})
    assert m["clis"] == ["claude", "copilot"]


# ── CopilotAdapter ──


def test_copilot_creates_agents_md(tmp_path: Path):
    CopilotAdapter().deploy(tmp_path, _selections(), _ctx())
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    text = agents_md.read_text()
    assert "# demo" in text
    assert "<!-- agent-foundry -->" in text
    assert "<!-- rule: coding-style.md -->" in text  # rule body embedded
    assert "uv sync" in text  # python env command rendered
    # No Claude-only artifacts
    assert not (tmp_path / ".claude").exists()


def test_copilot_update_is_idempotent(tmp_path: Path):
    for _ in range(2):
        CopilotAdapter().deploy(tmp_path, _selections(), _ctx())
    text = (tmp_path / "AGENTS.md").read_text()
    assert text.count("<!-- agent-foundry -->") == 1
    assert text.count("<!-- /agent-foundry -->") == 1
    assert not (tmp_path / "AGENTS.md.old").exists()


def test_copilot_preserves_user_content(tmp_path: Path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# My Project\n\nHand-written guidance.\n")
    CopilotAdapter().deploy(tmp_path, _selections(), _ctx())
    text = agents_md.read_text()
    assert "Hand-written guidance." in text  # user content kept
    assert "<!-- agent-foundry -->" in text  # foundry block prepended
    assert (tmp_path / "AGENTS.md.old").exists()  # original backed up


# ── End-to-end multi-CLI via cmd_init ──


def test_cmd_init_multi_cli(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    ok = cmd_init(tmp_path, interactive=False, clis=["claude", "copilot"])
    assert ok
    assert (tmp_path / ".claude" / "rules").is_dir()      # Claude target
    assert (tmp_path / "AGENTS.md").exists()              # Copilot target
    import json
    manifest = json.loads((tmp_path / ".claude" / "setup-manifest.json").read_text())
    assert manifest["clis"] == ["claude", "copilot"]


def test_cmd_init_copilot_only_skips_claude_dir(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    ok = cmd_init(tmp_path, interactive=False, clis=["copilot"])
    assert ok
    assert (tmp_path / "AGENTS.md").exists()
    # Copilot-only: no .claude/ config tree (only the .foundry payload may exist)
    assert not (tmp_path / ".claude" / "rules").exists()
