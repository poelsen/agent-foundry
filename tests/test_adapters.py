"""Tests for the multi-CLI adapter layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import pytest

from foundry.adapters import (
    ADAPTERS,
    DEFAULT_CLIS,
    ClaudeAdapter,
    CopilotAdapter,
    DeployContext,
    Selections,
)
from foundry.adapters.base import AGENTS_MD, AGENTS_SKILLS, MCP_JSON
from foundry.console import QuitSetup
from foundry.manifest import migrate_manifest
from foundry.orchestrator import _deploy_to_clis, _select_clis, cmd_init


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


def _deploy_copilot(project: Path, sel: Selections) -> None:
    """Deploy like cmd_init does: adapter first, then the shared outputs."""
    ok, _ = _deploy_to_clis(project, [CopilotAdapter()], sel, _ctx())
    assert ok


# ── Registry ──


def test_registry_has_all_targets():
    assert set(ADAPTERS) == {"claude", "copilot", "codex"}
    assert DEFAULT_CLIS == ["claude"]


def test_supported_artifacts_differ():
    assert "agents" in ClaudeAdapter().supported_artifacts()
    # Copilot consumes rules, mcp, and portable skills — but not subagents/hooks
    assert CopilotAdapter().supported_artifacts() == {"rules", "mcp", "skills"}
    assert "agents" not in CopilotAdapter().supported_artifacts()


def test_shared_outputs_declared():
    assert ClaudeAdapter.shared_outputs == {MCP_JSON}
    assert CopilotAdapter.shared_outputs == {AGENTS_MD, AGENTS_SKILLS, MCP_JSON}


# ── CopilotAdapter: portable skills → shared .agents/skills/ ──


def test_copilot_deploys_portable_skill_sanitized(tmp_path: Path):
    _deploy_copilot(tmp_path, _selections(skills=["megamind-deep"]))
    skill_md = tmp_path / ".agents" / "skills" / "megamind-deep" / "SKILL.md"
    assert skill_md.exists()
    text = skill_md.read_text()
    assert "name: megamind-deep" in text            # frontmatter preserved
    assert "model:" not in text.split("---", 2)[1]  # model stripped from frontmatter
    assert not (tmp_path / ".github" / "skills").exists()  # no longer the Copilot root


def test_copilot_skips_non_portable_skill(tmp_path: Path):
    # prj-new is Claude-coupled — must not land in the shared skill root
    _deploy_copilot(tmp_path, _selections(skills=["prj-new"]))
    assert not (tmp_path / ".agents" / "skills" / "prj-new").exists()


def test_copilot_removes_deselected_skill(tmp_path: Path):
    _deploy_copilot(tmp_path, _selections(skills=["megamind-deep"]))
    assert (tmp_path / ".agents" / "skills" / "megamind-deep").exists()
    # Re-run without it selected → foundry-managed copy is reconciled away
    _deploy_copilot(tmp_path, _selections(skills=[]))
    assert not (tmp_path / ".agents" / "skills" / "megamind-deep").exists()


def test_copilot_migrates_legacy_github_skills(tmp_path: Path):
    legacy = tmp_path / ".github" / "skills"
    (legacy / "megamind-deep").mkdir(parents=True)
    (legacy / "megamind-deep" / "SKILL.md").write_text("old copy")
    (legacy / "team-skill").mkdir()  # project-owned — must survive
    _deploy_copilot(tmp_path, _selections(skills=["megamind-deep"]))
    assert not (legacy / "megamind-deep").exists()
    assert (legacy / "team-skill").is_dir()
    assert (tmp_path / ".agents" / "skills" / "megamind-deep" / "SKILL.md").exists()


def test_copilot_removes_emptied_legacy_skill_dir(tmp_path: Path):
    (tmp_path / ".github" / "skills" / "megamind-creative").mkdir(parents=True)
    (tmp_path / ".github" / "workflows").mkdir()
    _deploy_copilot(tmp_path, _selections())
    assert not (tmp_path / ".github" / "skills").exists()
    assert (tmp_path / ".github" / "workflows").is_dir()  # rest of .github untouched


# ── _select_clis ──


def test_select_clis_non_interactive_returns_saved():
    assert _select_clis(["copilot"], interactive=False) == ["copilot"]


def test_select_clis_filters_unknown_and_falls_back(capsys):
    assert _select_clis(["bogus"], interactive=False) == ["claude"]
    assert "Unknown CLI target(s) ignored: bogus" in capsys.readouterr().out
    assert _select_clis([], interactive=False) == ["claude"]


def test_select_clis_quit_propagates(monkeypatch):
    def _quit(*_args, **_kwargs):
        raise QuitSetup()
    monkeypatch.setattr("foundry.orchestrator.toggle_menu", _quit)
    with pytest.raises(QuitSetup):
        _select_clis(["claude"], interactive=True)


# ── manifest migration ──


def test_migrate_backfills_clis():
    assert migrate_manifest({"version": "1.0"})["clis"] == ["claude"]


def test_migrate_preserves_explicit_clis():
    m = migrate_manifest({"version": "1.0", "clis": ["claude", "copilot"]})
    assert m["clis"] == ["claude", "copilot"]


# ── CopilotAdapter: AGENTS.md ──


def test_copilot_creates_agents_md(tmp_path: Path):
    _deploy_copilot(tmp_path, _selections())
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    text = agents_md.read_text()
    assert "# demo" in text
    assert "<!-- agent-foundry -->" in text
    assert "<!-- rule: coding-style.md -->" in text  # rule body embedded
    assert "uv sync" in text  # python env command rendered
    # No Claude-only artifacts
    assert not (tmp_path / ".claude").exists()


def test_copilot_omits_claude_only_rules(tmp_path: Path):
    _deploy_copilot(tmp_path, _selections(base=["coding-style.md", "agents.md", "hooks.md"]))
    text = (tmp_path / "AGENTS.md").read_text()
    assert "<!-- rule: coding-style.md -->" in text
    assert "<!-- rule: agents.md -->" not in text  # Task tool / subagent roster
    assert "<!-- rule: hooks.md -->" not in text   # .claude/settings.json hooks


def test_copilot_update_is_idempotent(tmp_path: Path):
    for _ in range(2):
        _deploy_copilot(tmp_path, _selections())
    text = (tmp_path / "AGENTS.md").read_text()
    assert text.count("<!-- agent-foundry -->") == 1
    assert text.count("<!-- /agent-foundry -->") == 1
    assert not (tmp_path / "AGENTS.md.old").exists()


def test_copilot_preserves_user_content(tmp_path: Path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# My Project\n\nHand-written guidance.\n")
    _deploy_copilot(tmp_path, _selections())
    text = agents_md.read_text()
    assert "Hand-written guidance." in text  # user content kept
    # foundry block prepended, like the CLAUDE.md merge
    assert text.index("<!-- agent-foundry -->") < text.index("Hand-written guidance.")
    assert (tmp_path / "AGENTS.md.old").exists()  # original backed up


# ── Skipped-artifact report ──


def test_claude_skips_nothing():
    sel = _selections(agents=["doc-updater.md"], hooks=["ruff-format.sh"],
                      skills=["prj-new"], plugins=["feature-dev"])
    assert ClaudeAdapter().skipped(sel) == []


def test_copilot_reports_unsupported_and_claude_only():
    sel = _selections(base=["coding-style.md", "agents.md"], agents=["doc-updater.md"],
                      hooks=["ruff-format.sh"], skills=["megamind-deep", "prj-new"])
    by_artifact = {s.artifact: s for s in CopilotAdapter().skipped(sel)}
    assert by_artifact["agents"].items == ["doc-updater.md"]
    assert not by_artifact["agents"].claude_only
    assert by_artifact["hooks"].items == ["ruff-format.sh"]
    assert by_artifact["skills"].items == ["prj-new"]  # megamind-deep is portable
    assert by_artifact["skills"].claude_only
    assert by_artifact["rules"].items == ["agents.md"]


def test_skipped_report_printed(tmp_path: Path, capsys):
    sel = _selections(agents=["doc-updater.md"], skills=["prj-new"])
    _deploy_copilot(tmp_path, sel)
    out = capsys.readouterr().out
    assert "Not deployed" in out
    assert "no support for agents (1)" in out
    assert "Claude-only skills — prj-new" in out


def test_skipped_report_notes_copilot_reads_claude_skills(tmp_path: Path, capsys):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    assert cmd_init(tmp_path, interactive=False, clis=["claude", "copilot"])
    out = capsys.readouterr().out
    assert "GitHub Copilot CLI still loads them from .claude/skills/" in out


def test_non_claude_run_keeps_registered_private_sources(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    registered = [{"path": str(tmp_path / "company-config"), "prefix": "company",
                   "rules": ["templates/custom.md"]}]
    manifest_path = tmp_path / ".claude" / "setup-manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps({"version": "1.0", "clis": ["copilot"],
                                         "private_sources": registered}))
    assert cmd_init(tmp_path, interactive=False)
    assert json.loads(manifest_path.read_text())["private_sources"] == registered


def test_private_sources_reported_for_non_claude(tmp_path: Path, capsys):
    ctx = _ctx(cli_private_sources=[(str(tmp_path), "company")])
    ok, _ = _deploy_to_clis(tmp_path, [CopilotAdapter()], _selections(), ctx)
    assert ok
    assert "Private sources deploy only for Claude Code" in capsys.readouterr().out


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
