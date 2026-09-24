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
    assert set(ADAPTERS) == {"claude", "copilot", "codex", "agy"}
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


def _legacy_skill(root: Path, name: str, skill_name: str | None = None) -> Path:
    d = root / ".github" / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {skill_name or name}\ndescription: x\n---\nbody\n")
    return d


def test_copilot_migrates_legacy_github_skills(tmp_path: Path):
    legacy = _legacy_skill(tmp_path, "megamind-deep")
    (tmp_path / ".github" / "skills" / "team-skill").mkdir()  # project-owned — must survive
    _deploy_copilot(tmp_path, _selections(skills=["megamind-deep"]))
    assert not legacy.exists()
    assert (tmp_path / ".github" / "skills" / "team-skill").is_dir()
    assert (tmp_path / ".agents" / "skills" / "megamind-deep" / "SKILL.md").exists()


def test_copilot_keeps_same_named_dir_that_isnt_the_foundry_skill(tmp_path: Path):
    own = _legacy_skill(tmp_path, "megamind-deep", skill_name="our-deep-review")
    _deploy_copilot(tmp_path, _selections(skills=["megamind-deep"]))
    assert own.is_dir()


def test_copilot_removes_emptied_legacy_skill_dir(tmp_path: Path):
    _legacy_skill(tmp_path, "megamind-creative")
    (tmp_path / ".github" / "workflows").mkdir()
    _deploy_copilot(tmp_path, _selections())
    assert not (tmp_path / ".github" / "skills").exists()
    assert (tmp_path / ".github" / "workflows").is_dir()  # rest of .github untouched


# ── _select_clis ──


def test_select_clis_non_interactive_returns_saved():
    assert _select_clis(["copilot"], interactive=False) == ["copilot"]


def test_select_clis_canonical_order_without_duplicates():
    # Claude (which may abort on an unmarked CLAUDE.md) always runs first
    assert _select_clis(["codex", "claude", "codex"], interactive=False) == ["claude", "codex"]


def test_claude_abort_leaves_no_other_cli_files(tmp_path: Path):
    (tmp_path / "CLAUDE.md").write_text("# Mine, no foundry marker\n")
    assert not cmd_init(tmp_path, interactive=False, clis=["codex", "claude"])
    assert not (tmp_path / ".codex").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_unknown_only_clis_is_an_error_not_claude(tmp_path: Path, capsys):
    assert not cmd_init(tmp_path, interactive=False, clis=["codx"])
    assert "Unknown CLI target(s): codx" in capsys.readouterr().err
    assert not (tmp_path / "CLAUDE.md").exists()


def test_typo_among_valid_clis_never_drops_a_target(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    assert cmd_init(tmp_path, interactive=False, clis=["claude", "codex"])
    assert not cmd_init(tmp_path, interactive=False, clis=["claude", "codx"])
    assert (tmp_path / ".codex").is_dir()  # nothing undeployed
    manifest = json.loads((tmp_path / ".claude" / "setup-manifest.json").read_text())
    assert manifest["clis"] == ["claude", "codex"]


def test_interactive_drop_needs_confirmation(tmp_path: Path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    assert cmd_init(tmp_path, interactive=False, clis=["claude", "codex"])
    # Accept "Reconfigure?", decline only the drop
    monkeypatch.setattr("foundry.orchestrator.confirm",
                        lambda msg, **k: not msg.startswith("Drop "))
    monkeypatch.setattr("foundry.orchestrator.toggle_menu", lambda t, items, sel, **k: {0})
    monkeypatch.setattr("foundry.selection.toggle_menu", lambda t, items, sel, **k: set(sel))
    monkeypatch.setattr("builtins.input", lambda *_: "")
    assert cmd_init(tmp_path, interactive=True)  # user unticked Codex, then declined the drop
    assert (tmp_path / ".codex").is_dir()
    assert "Keeping OpenAI Codex CLI as a target." in capsys.readouterr().out


def test_main_exit_codes(tmp_path: Path):
    import subprocess
    setup = Path(__file__).parent.parent / "tools" / "setup.py"
    typo = subprocess.run([sys.executable, str(setup), "init", str(tmp_path), "--non-interactive",
                           "--clis", "claude,codx"], capture_output=True, text=True)
    assert typo.returncode == 2 and "codx" in typo.stderr
    (tmp_path / "CLAUDE.md").write_text("# no marker\n")
    skipped = subprocess.run([sys.executable, str(setup), "init", str(tmp_path),
                              "--non-interactive"], capture_output=True, text=True)
    assert skipped.returncode == 3  # nothing applied by design → update-foundry keeps the old version


def test_private_source_registered_on_non_claude_run(tmp_path: Path):
    src = tmp_path / "company-config"
    (src / "rule-library" / "templates").mkdir(parents=True)
    (src / "rule-library" / "templates" / "house.md").write_text("# House rule\n")
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text('name = "x"\n')
    assert cmd_init(project, interactive=False, clis=["codex"],
                    cli_private_sources=[(str(src), "company")])
    manifest = json.loads((project / ".claude" / "setup-manifest.json").read_text())
    (entry,) = manifest["private_sources"]
    assert entry["prefix"] == "company" and entry["rules"] == ["templates/house.md"]
    assert cmd_init(project, interactive=False, clis=["claude", "codex"])
    assert (project / ".claude" / "rules" / "company-house.md").exists()


def test_claude_drop_notice_keeps_manifest_advice(tmp_path: Path, capsys):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    assert cmd_init(tmp_path, interactive=False, clis=["claude", "codex"])
    assert cmd_init(tmp_path, interactive=False, clis=["codex"])
    assert "keep .claude/setup-manifest.json and .claude/VERSION" in capsys.readouterr().out


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


def test_ownership_record_saved_even_when_empty(tmp_path: Path):
    """A manifest without deployed_mcp would be mistaken for a pre-upgrade one
    and its selection claimed as foundry-written .mcp.json entries."""
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    manifest_path = tmp_path / ".claude" / "setup-manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps({"version": "1.0", "clis": ["codex"], "deployed_mcp": {},
                                         "mcp_servers": ["memory"]}))
    assert cmd_init(tmp_path, interactive=False)
    assert json.loads(manifest_path.read_text())["deployed_mcp"] == {}
    from foundry.deploy import selected_mcp_servers
    own = {"mcpServers": {"memory": selected_mcp_servers(["memory"])["memory"]}}
    (tmp_path / ".mcp.json").write_text(json.dumps(own))  # the project's own, identical
    data = json.loads(manifest_path.read_text())
    data["mcp_servers"] = []
    manifest_path.write_text(json.dumps(data))
    assert cmd_init(tmp_path, interactive=False, clis=["claude", "codex"])
    assert json.loads((tmp_path / ".mcp.json").read_text()) == own


def test_malformed_manifest_mcp_fields_dont_crash():
    from foundry.orchestrator import _mcp_state
    assert _mcp_state({"mcp_servers": None}) == {".mcp.json": {}}
    assert _mcp_state({"deployed_mcp": None, "mcp_servers": ["memory", 3]}) == {
        ".mcp.json": {"memory": None}}
    assert _mcp_state({"deployed_mcp": {".mcp.json": None, "agy": {}}}) == {"agy": {}}
