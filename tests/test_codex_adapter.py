"""Tests for the OpenAI Codex CLI adapter."""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import pytest

from foundry.adapters import CodexAdapter, DeployContext, Selections
from foundry.adapters import codex as codex_mod
from foundry.orchestrator import _deploy_to_clis, cmd_init
from foundry.paths import AGENTS_DIR


def _selections(**overrides) -> Selections:
    base = {
        "base": ["coding-style.md"], "modular": {"lang": ["python.md"]},
        "agents": [], "skills": [], "learned": [], "hooks": [], "plugins": [],
        "mcp_servers": [], "features": [], "langs": {"python.md"},
        "project_name": "demo", "version": "9999.99.99",
    }
    base.update(overrides)
    return Selections(**base)


def _ctx() -> DeployContext:
    return DeployContext(interactive=False, force=False, private_prefixes=[],
                         pending_private=[], existing_private=[], cli_private_sources=[])


def _deploy(project: Path, **overrides) -> None:
    ok, _ = _deploy_to_clis(project, [CodexAdapter()], _selections(**overrides), _ctx())
    assert ok


@pytest.fixture(autouse=True)
def _untrusted_codex_home(tmp_path_factory, monkeypatch):
    """Point CODEX_HOME at an empty dir so the user's real trust list never leaks in."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path_factory.mktemp("codex-home")))


def _toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


# ── Adapter contract ──


def test_contract():
    adapter = CodexAdapter()
    assert adapter.id == "codex"
    assert adapter.agents_md_limit == 32 * 1024
    assert {"agents", "hooks", "mcp", "skills", "rules"} <= adapter.supported_artifacts()
    assert "plugins" not in adapter.supported_artifacts()


# ── Agents → .codex/agents/*.toml ──


@pytest.mark.parametrize("agent", sorted(f.name for f in AGENTS_DIR.glob("*.md")))
def test_every_foundry_agent_converts_to_valid_toml(agent: str):
    rendered = codex_mod.render_agent_toml(AGENTS_DIR / agent)
    assert rendered is not None
    role = tomllib.loads(rendered)
    # Codex rejects agent files with unknown keys, so only known ones appear
    assert set(role) <= {"name", "description", "developer_instructions", "sandbox_mode"}
    assert role["name"] == agent.removesuffix(".md")
    assert role["developer_instructions"].strip()


def test_read_only_agent_gets_read_only_sandbox(tmp_path: Path):
    _deploy(tmp_path, agents=["code-reviewer-python.md", "tdd-guide-python.md"])
    reviewer = _toml(tmp_path / ".codex/agents/code-reviewer-python.toml")
    assert reviewer["sandbox_mode"] == "read-only"       # tools: Read, Grep, Glob, Bash
    assert "sandbox_mode" not in _toml(tmp_path / ".codex/agents/tdd-guide-python.toml")
    assert "model" not in reviewer                        # Claude model names dropped


def test_agent_bodies_rewritten_for_codex(tmp_path: Path):
    _deploy(tmp_path, agents=["doc-updater.md"])
    role = _toml(tmp_path / ".codex/agents/doc-updater.toml")
    assert "$update-codemaps" in role["developer_instructions"]
    assert "/update-codemaps" not in role["developer_instructions"]


def test_deselected_agent_pruned_project_agent_kept(tmp_path: Path):
    own = tmp_path / ".codex/agents/team-helper.toml"
    own.parent.mkdir(parents=True)
    own.write_text('name = "team-helper"\n')
    _deploy(tmp_path, agents=["doc-updater.md"])
    assert (tmp_path / ".codex/agents/doc-updater.toml").exists()
    _deploy(tmp_path, agents=[])
    assert not (tmp_path / ".codex/agents/doc-updater.toml").exists()
    assert own.read_text() == 'name = "team-helper"\n'


def test_unmarked_same_name_agent_not_overwritten(tmp_path: Path):
    own = tmp_path / ".codex/agents/doc-updater.toml"
    own.parent.mkdir(parents=True)
    own.write_text('name = "doc-updater"\n')
    _deploy(tmp_path, agents=["doc-updater.md"])
    assert own.read_text() == 'name = "doc-updater"\n'


# ── MCP → .codex/config.toml ──


def test_mcp_servers_written_in_codex_schema(tmp_path: Path):
    _deploy(tmp_path, mcp_servers=["memory", "vercel", "firecrawl"])
    servers = _toml(tmp_path / ".codex/config.toml")["mcp_servers"]
    assert servers["memory"] == {"command": "npx",
                                 "args": ["-y", "@modelcontextprotocol/server-memory"]}
    assert servers["vercel"] == {"url": "https://mcp.vercel.com"}  # no `type` key
    assert servers["firecrawl"]["env"] == {"FIRECRAWL_API_KEY": "YOUR_FIRECRAWL_KEY_HERE"}
    assert not (tmp_path / ".mcp.json").exists()  # Codex doesn't read it


def test_mcp_block_preserves_project_config(tmp_path: Path):
    config = tmp_path / ".codex/config.toml"
    config.parent.mkdir()
    config.write_text('model = "gpt-5.5"\n\n[profiles.fast]\nmodel_reasoning_effort = "low"\n')
    for _ in range(2):
        _deploy(tmp_path, mcp_servers=["memory"])
    text = config.read_text()
    assert text.count(codex_mod._BLOCK_START) == 1
    data = tomllib.loads(text)
    assert data["model"] == "gpt-5.5"
    assert data["profiles"]["fast"] == {"model_reasoning_effort": "low"}
    assert "memory" in data["mcp_servers"]
    _deploy(tmp_path, mcp_servers=[])
    assert codex_mod._BLOCK_START not in config.read_text()
    assert tomllib.loads(config.read_text())["model"] == "gpt-5.5"


def test_config_removed_when_only_foundry_block(tmp_path: Path):
    _deploy(tmp_path, mcp_servers=["memory"])
    _deploy(tmp_path, mcp_servers=[])
    assert not (tmp_path / ".codex/config.toml").exists()


def test_project_defined_server_wins(tmp_path: Path, capsys):
    config = tmp_path / ".codex/config.toml"
    config.parent.mkdir()
    config.write_text('[mcp_servers.memory]\ncommand = "my-memory"\n')
    _deploy(tmp_path, mcp_servers=["memory"])
    assert _toml(config)["mcp_servers"]["memory"] == {"command": "my-memory"}
    assert "Left project-defined mcp_servers.memory" in capsys.readouterr().out


def test_unparseable_config_left_alone(tmp_path: Path, capsys):
    config = tmp_path / ".codex/config.toml"
    config.parent.mkdir()
    config.write_text("not = [valid\n")
    _deploy(tmp_path, mcp_servers=["memory"])
    assert config.read_text() == "not = [valid\n"
    assert "doesn't parse" in capsys.readouterr().out


# ── Hooks → .codex/hooks.json ──


def test_hooks_json_and_scripts(tmp_path: Path):
    _deploy(tmp_path, hooks=["ruff-format.sh", "mypy-check.sh"])
    data = json.loads((tmp_path / ".codex/hooks.json").read_text())
    (group,) = data["hooks"]["PostToolUse"]
    assert group["matcher"] == "apply_patch|Edit|Write"
    commands = [h["command"] for h in group["hooks"]]
    assert all("git rev-parse --show-toplevel" in c for c in commands)
    assert commands[0].endswith('/.codex/hooks/agent-foundry/ruff-format.sh"')
    scripts = tmp_path / ".codex/hooks/agent-foundry"
    assert os.access(scripts / "ruff-format.sh", os.X_OK)
    assert (scripts / "_edited-files.sh").is_file()  # helper the scripts source


def test_project_hooks_kept_foundry_hooks_reconciled(tmp_path: Path):
    hooks_json = tmp_path / ".codex/hooks.json"
    hooks_json.parent.mkdir()
    own = {"matcher": "Bash", "hooks": [{"type": "command", "command": "./audit.sh"}]}
    hooks_json.write_text(json.dumps({"hooks": {"PostToolUse": [own]}}))
    _deploy(tmp_path, hooks=["ruff-format.sh"])
    groups = json.loads(hooks_json.read_text())["hooks"]["PostToolUse"]
    assert own in groups and len(groups) == 2
    _deploy(tmp_path, hooks=[])
    assert json.loads(hooks_json.read_text())["hooks"]["PostToolUse"] == [own]
    assert not (tmp_path / ".codex/hooks/agent-foundry").exists()


def test_hooks_json_removed_when_only_foundry(tmp_path: Path):
    _deploy(tmp_path, hooks=["ruff-format.sh"])
    _deploy(tmp_path, hooks=[])
    assert not (tmp_path / ".codex/hooks.json").exists()


def test_unparseable_hooks_json_left_alone(tmp_path: Path):
    hooks_json = tmp_path / ".codex/hooks.json"
    hooks_json.parent.mkdir()
    hooks_json.write_text("{broken")
    _deploy(tmp_path, hooks=["ruff-format.sh"])
    assert hooks_json.read_text() == "{broken"


def test_unexpected_hooks_json_shape_left_alone(tmp_path: Path):
    hooks_json = tmp_path / ".codex/hooks.json"
    hooks_json.parent.mkdir()
    hooks_json.write_text('{"hooks": {"PostToolUse": {"not": "a list"}}}')
    _deploy(tmp_path, hooks=["ruff-format.sh"])
    assert json.loads(hooks_json.read_text()) == {"hooks": {"PostToolUse": {"not": "a list"}}}


# ── Trust ──


def test_trust_hint_when_untrusted(tmp_path: Path, capsys):
    _deploy(tmp_path, agents=["doc-updater.md"], hooks=["ruff-format.sh"])
    out = capsys.readouterr().out
    assert "only in trusted projects" in out
    assert f'[projects."{tmp_path}"]' in out
    assert "/hooks" in out


def test_no_trust_hint_when_trusted(tmp_path: Path, capsys, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(f'[projects."{tmp_path}"]\ntrust_level = "trusted"\n')
    monkeypatch.setenv("CODEX_HOME", str(home))
    assert codex_mod.project_trusted(tmp_path)
    _deploy(tmp_path, agents=["doc-updater.md"])
    assert "only in trusted projects" not in capsys.readouterr().out


def test_no_trust_hint_without_codex_dir_content(tmp_path: Path, capsys):
    _deploy(tmp_path)  # AGENTS.md + .agents/skills only — load untrusted
    assert "trusted" not in capsys.readouterr().out


# ── Shared outputs for Codex ──


def test_codex_gets_agents_md_and_command_skills(tmp_path: Path):
    _deploy(tmp_path, skills=["megamind-deep", "prj-new"])
    assert "<!-- agent-foundry -->" in (tmp_path / "AGENTS.md").read_text()
    skills = tmp_path / ".agents/skills"
    assert (skills / "megamind-deep/SKILL.md").exists()
    assert not (skills / "prj-new").exists()
    command = (skills / "update-codemaps/SKILL.md").read_text()
    assert command.startswith("---\nname: update-codemaps\ndescription: ")
    assert "**Model:**" not in command


def test_agents_md_over_codex_limit_warns(tmp_path: Path, capsys):
    (tmp_path / "AGENTS.md").write_text("# Big\n\n" + "x" * 40_000 + "\n")
    _deploy(tmp_path)
    assert "OpenAI Codex CLI reads only the first 32,768" in capsys.readouterr().out


def test_cmd_init_codex_only(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    assert cmd_init(tmp_path, interactive=False, clis=["codex"])
    assert (tmp_path / "AGENTS.md").exists()
    assert list((tmp_path / ".codex/agents").glob("*-python.toml"))  # auto-selected by language
    assert (tmp_path / ".codex/hooks.json").exists()                  # ruff/mypy by language
    assert not (tmp_path / ".claude" / "rules").exists()
