"""Tests for the Google Antigravity CLI (agy) adapter."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import pytest

from foundry.adapters import AntigravityAdapter, DeployContext, Selections
from foundry.adapters import antigravity as agy_mod
from foundry.orchestrator import _deploy_to_clis, cmd_init
from foundry.paths import AGENTS_DIR


def _selections(**overrides) -> Selections:
    base = {
        "base": ["coding-style.md"], "modular": {"lang": ["python.md"]},
        "agents": [], "skills": [], "learned": [], "hooks": [], "plugins": [],
        "mcp_servers": [], "langs": {"python.md"},
        "project_name": "demo", "version": "9999.99.99",
    }
    base.update(overrides)
    return Selections(**base)


_MCP_STATE: dict[Path, dict] = {}  # stands in for the manifest's deployed_mcp between runs


def _deploy(project: Path, **overrides) -> None:
    ctx = DeployContext(interactive=False, force=False, private_prefixes=[],
                        pending_private=[], existing_private=[], cli_private_sources=[],
                        mcp_state=_MCP_STATE.setdefault(project, {}))
    ok, _ = _deploy_to_clis(project, [AntigravityAdapter()], _selections(**overrides), ctx)
    assert ok


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    """Keep the user's real Antigravity trust list out of the tests."""
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))


def _frontmatter(text: str) -> str:
    return text.split("\n---\n", 1)[0]


# ── Adapter contract ──


def test_contract():
    adapter = AntigravityAdapter()
    assert adapter.id == "agy"
    assert adapter.agents_md_limit == 24_000
    assert {"agents", "hooks", "mcp", "skills", "rules"} <= adapter.supported_artifacts()


# ── Agents → .agents/agents/*.md ──


@pytest.mark.parametrize("agent", sorted(f.name for f in AGENTS_DIR.glob("*.md")))
def test_every_agent_has_one_system_prompt_heading(agent: str):
    rendered = agy_mod.render_agent_md(AGENTS_DIR / agent)
    assert rendered is not None
    body = rendered.split("\n---\n", 1)[1]
    in_fence, h1 = False, []
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("# "):
            h1.append(line)
    assert h1 == ["# System Prompt"]  # agy splits prompts on H1s
    assert f'name: "{agent.removesuffix(".md")}"' in _frontmatter(rendered)
    assert "model:" not in _frontmatter(rendered)


def test_read_only_agent_gets_mapped_read_tools(tmp_path: Path):
    _deploy(tmp_path, agents=["code-reviewer-python.md", "tdd-guide-python.md"])
    reviewer = (tmp_path / ".agents/agents/code-reviewer-python.md").read_text()
    assert "tools: [find_by_name, grep_search, list_dir, run_command, view_file]" in reviewer
    # Write-capable agents inherit Antigravity's default toolset
    assert "tools:" not in _frontmatter((tmp_path / ".agents/agents/tdd-guide-python.md").read_text())


def test_code_fence_comments_not_demoted():
    body = "# Title\n\n```bash\n# keep me\n```\n"
    assert agy_mod._demote_h1(body) == "## Title\n\n```bash\n# keep me\n```"


def test_agent_prune_keeps_project_agents(tmp_path: Path):
    own = tmp_path / ".agents/agents/team.md"
    own.parent.mkdir(parents=True)
    own.write_text("---\nname: team\ndescription: ours\n---\n# System Prompt\nhi\n")
    _deploy(tmp_path, agents=["doc-updater.md"])
    _deploy(tmp_path, agents=[])
    assert not (tmp_path / ".agents/agents/doc-updater.md").exists()
    assert own.exists()


# ── MCP → .agents/mcp_config.json ──


def _mcp(project: Path) -> dict:
    return json.loads((project / ".agents/mcp_config.json").read_text())["mcpServers"]


def test_mcp_servers_in_agy_schema(tmp_path: Path):
    _deploy(tmp_path, mcp_servers=["memory", "vercel"])
    servers = _mcp(tmp_path)
    assert servers["memory"] == {"command": "npx",
                                 "args": ["-y", "@modelcontextprotocol/server-memory"]}
    assert servers["vercel"] == {"serverUrl": "https://mcp.vercel.com"}  # not url/type


def test_filled_in_api_key_survives_updates(tmp_path: Path):
    _deploy(tmp_path, mcp_servers=["firecrawl"])
    path = tmp_path / ".agents/mcp_config.json"
    data = json.loads(path.read_text())
    data["mcpServers"]["firecrawl"]["env"]["FIRECRAWL_API_KEY"] = "real-key"
    path.write_text(json.dumps(data))
    _deploy(tmp_path, mcp_servers=["firecrawl"])  # never resets the real key
    assert _mcp(tmp_path)["firecrawl"]["env"]["FIRECRAWL_API_KEY"] == "real-key"


def test_otherwise_edited_server_is_the_projects(tmp_path: Path, capsys):
    _deploy(tmp_path, mcp_servers=["memory"])
    path = tmp_path / ".agents/mcp_config.json"
    data = json.loads(path.read_text())
    data["mcpServers"]["memory"]["args"].append("--custom")
    path.write_text(json.dumps(data))
    _deploy(tmp_path, mcp_servers=["memory"])
    assert "--custom" in _mcp(tmp_path)["memory"]["args"]
    assert "Kept the project's own mcpServers.memory" in capsys.readouterr().out
    _deploy(tmp_path, mcp_servers=[])  # deselecting doesn't delete the project's entry
    assert "memory" in _mcp(tmp_path)


def test_catalog_change_reaches_deployed_entry(tmp_path: Path, monkeypatch):
    ctx_state: dict = {}
    agy_mod._deploy_mcp(tmp_path, ["memory"], ctx_state)
    real = agy_mod.selected_mcp_servers

    def bumped(servers):
        catalog = real(servers)
        if "memory" in catalog:
            catalog["memory"]["args"] = ["-y", "@modelcontextprotocol/server-memory@2"]
        return catalog

    monkeypatch.setattr(agy_mod, "selected_mcp_servers", bumped)
    agy_mod._deploy_mcp(tmp_path, ["memory"], ctx_state)  # recorded → still the foundry's
    assert _mcp(tmp_path)["memory"]["args"][-1].endswith("@2")
    agy_mod._deploy_mcp(tmp_path, [], ctx_state)
    assert not (tmp_path / ".agents/mcp_config.json").exists()


def test_project_configured_catalog_server_is_never_removed(tmp_path: Path):
    """Equal to the catalog but never recorded as deployed → the project's."""
    path = tmp_path / ".agents/mcp_config.json"
    path.parent.mkdir()
    own = {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]}
    path.write_text(json.dumps({"mcpServers": {"memory": own}}))
    _deploy(tmp_path, mcp_servers=[])
    assert _mcp(tmp_path)["memory"] == own


def test_deselected_server_with_filled_key_is_kept(tmp_path: Path, capsys):
    _deploy(tmp_path, mcp_servers=["firecrawl"])
    path = tmp_path / ".agents/mcp_config.json"
    data = json.loads(path.read_text())
    data["mcpServers"]["firecrawl"]["env"]["FIRECRAWL_API_KEY"] = "real-key"
    path.write_text(json.dumps(data))
    _deploy(tmp_path, mcp_servers=[])
    assert _mcp(tmp_path)["firecrawl"]["env"]["FIRECRAWL_API_KEY"] == "real-key"
    assert "holds a value you filled in" in capsys.readouterr().out


def test_mcp_config_removed_when_only_foundry(tmp_path: Path):
    _deploy(tmp_path, mcp_servers=["memory"])
    _deploy(tmp_path, mcp_servers=[])
    assert not (tmp_path / ".agents/mcp_config.json").exists()


def test_mcp_config_with_comments_left_alone(tmp_path: Path):
    path = tmp_path / ".agents/mcp_config.json"
    path.parent.mkdir()
    path.write_text('{ // agy allows comments\n "mcpServers": {} }')
    _deploy(tmp_path, mcp_servers=["memory"])
    assert "// agy allows comments" in path.read_text()


# ── Hooks → .agents/hooks.json ──


def test_hooks_json_named_entry(tmp_path: Path):
    _deploy(tmp_path, hooks=["ruff-format.sh"])
    data = json.loads((tmp_path / ".agents/hooks.json").read_text())
    (group,) = data["agent-foundry"]["PostToolUse"]
    assert group["matcher"] == "write_to_file|replace_file_content|multi_replace_file_content"
    # `bash <script>` reads the same under sh -c and cmd /c; the script prints `{}`
    assert group["hooks"][0]["command"] == "bash agent-foundry/hooks/ruff-format.sh"
    scripts = tmp_path / ".agents/agent-foundry/hooks"
    assert os.access(scripts / "ruff-format.sh", os.X_OK)
    assert (scripts / "_edited-files.sh").is_file()


def test_user_disabled_hook_stays_disabled(tmp_path: Path):
    _deploy(tmp_path, hooks=["ruff-format.sh"])
    path = tmp_path / ".agents/hooks.json"
    data = json.loads(path.read_text())
    data["agent-foundry"]["enabled"] = False
    path.write_text(json.dumps(data))
    _deploy(tmp_path, hooks=["ruff-format.sh", "mypy-check.sh"])
    assert json.loads(path.read_text())["agent-foundry"]["enabled"] is False


def test_copied_agent_survives_prune(tmp_path: Path):
    _deploy(tmp_path, agents=["architect-python.md"])
    agents = tmp_path / ".agents/agents"
    (agents / "team-architect.md").write_text((agents / "architect-python.md").read_text())
    _deploy(tmp_path, agents=[])
    assert (agents / "team-architect.md").exists()  # marker copied, but not a foundry name
    assert not (agents / "architect-python.md").exists()


def test_project_named_hooks_kept(tmp_path: Path):
    path = tmp_path / ".agents/hooks.json"
    path.parent.mkdir()
    own = {"lint-checker": {"PostToolUse": [{"matcher": "run_command",
                                             "hooks": [{"command": "./lint.sh"}]}]}}
    path.write_text(json.dumps(own))
    _deploy(tmp_path, hooks=["ruff-format.sh"])
    assert set(json.loads(path.read_text())) == {"lint-checker", "agent-foundry"}
    _deploy(tmp_path, hooks=[])
    assert json.loads(path.read_text()) == own
    assert not (tmp_path / ".agents/agent-foundry").exists()


# ── Trust ──


def test_trust_hint(tmp_path: Path, capsys):
    _deploy(tmp_path)
    assert "only in trusted workspaces" in capsys.readouterr().out


def test_trusted_parent_counts(tmp_path: Path, capsys):
    settings = Path(os.environ["HOME"]) / ".gemini/antigravity-cli/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"trustedWorkspaces": [str(tmp_path)]}))
    project = tmp_path / "proj"
    project.mkdir()
    assert agy_mod.workspace_trusted(project)
    _deploy(project)
    assert "only in trusted workspaces" not in capsys.readouterr().out


# ── Shared outputs and end to end ──


def test_agents_md_over_agy_limit_warns(tmp_path: Path, capsys):
    (tmp_path / "AGENTS.md").write_text("# Big\n\n" + "x" * 30_000 + "\n")
    _deploy(tmp_path)
    assert "Google Antigravity CLI reads only the first 24,000" in capsys.readouterr().out


def test_cmd_init_agy_only(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    assert cmd_init(tmp_path, interactive=False, clis=["agy"])
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".agents/skills/update-codemaps/SKILL.md").exists()
    assert list((tmp_path / ".agents/agents").glob("*-python.md"))
    assert (tmp_path / ".agents/hooks.json").exists()
    assert not (tmp_path / ".claude" / "rules").exists()


def test_dropping_agy_removes_its_config(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    assert cmd_init(tmp_path, interactive=False, clis=["agy"])
    assert (tmp_path / ".agents/agents").is_dir()
    (tmp_path / ".agents/agents/team.md").write_text("---\nname: team\n---\nours\n")
    assert cmd_init(tmp_path, interactive=False, clis=["claude"])
    assert not list((tmp_path / ".agents/agents").glob("*-python.md"))
    assert (tmp_path / ".agents/agents/team.md").exists()
    assert not (tmp_path / ".agents/hooks.json").exists()
    assert (tmp_path / "AGENTS.md").exists()              # Claude Code reads it too
    assert not (tmp_path / ".agents/skills/update-codemaps").exists()


def test_version_written_for_non_claude_targets(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    assert cmd_init(tmp_path, interactive=False, clis=["agy"])
    assert (tmp_path / ".claude/VERSION").read_text().strip()


def test_all_four_targets_in_one_run(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('name = "x"\n')
    assert cmd_init(tmp_path, interactive=False, clis=["claude", "copilot", "codex", "agy"])
    text = (tmp_path / "AGENTS.md").read_text()
    assert text.count("<!-- agent-foundry -->") == 1  # one shared block for three readers
    for path in (".claude/rules", ".codex/agents", ".agents/agents", ".agents/skills"):
        assert (tmp_path / path).is_dir(), path


@pytest.mark.parametrize("name, content", [("mcp_config.json", "{}"),
                                           ("mcp_config.json", '{"mcpServers": {}}'),
                                           ("hooks.json", "{}")])
def test_projects_empty_config_files_survive(tmp_path: Path, name: str, content: str):
    path = tmp_path / ".agents" / name
    path.parent.mkdir()
    path.write_text(content)
    _deploy(tmp_path)
    assert path.read_text() == content
