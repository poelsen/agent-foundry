"""Tests for outputs shared across CLIs (foundry/shared.py) and CLI-gated selection."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import pytest
import yaml

from foundry import shared
from foundry.adapters import ClaudeAdapter, CodexAdapter, CopilotAdapter, Selections
from foundry.paths import REPO_ROOT
from foundry.registry import BASE_RULES, CLAUDE_ONLY_RULES, PORTABLE_SKILLS
from foundry.selection import run_selection

HEAVY_MODULAR = {
    "lang": ["python.md", "nodejs.md"],
    "templates": ["desktop-gui-qt.md", "react-app.md", "rest-api.md"],
    "platform": ["github.md"],
    "security": ["enterprise.md"],
}


def _selections(**overrides) -> Selections:
    base = {
        "base": list(BASE_RULES),
        "modular": {"lang": ["python.md"], "templates": ["scripts.md"]},
        "agents": [], "skills": [], "learned": [], "hooks": [], "plugins": [],
        "mcp_servers": [], "langs": {"python.md"},
        "project_name": "demo", "version": "9999.99.99",
    }
    base.update(overrides)
    return Selections(**base)


def _rules_dir(project: Path) -> Path:
    return project / ".agents" / "rules"


# ── Budgeted AGENTS.md block ──


def test_default_selection_embeds_everything():
    block, overflow = shared.render_agents_block(_selections())
    assert overflow == []
    assert "<!-- rule: python.md -->" in block
    assert "### More rules" not in block


def test_claude_only_rules_never_rendered():
    names = [r.name for r in shared.portable_rules(_selections())]
    assert not CLAUDE_ONLY_RULES & set(names)
    assert "coding-style.md" in names


def test_priority_order_base_lang_then_templates():
    sel = _selections(modular=HEAVY_MODULAR)
    names = [r.name for r in shared.portable_rules(sel)]
    assert names.index("coding-style.md") < names.index("python.md")
    assert names.index("python.md") < names.index("github.md") < names.index("enterprise.md")
    assert names.index("enterprise.md") < names.index("desktop-gui-qt.md")


@pytest.mark.parametrize("budget", [6_000, 9_000, 12_000, shared.AGENTS_MD_BUDGET])
def test_block_never_exceeds_budget(budget: int):
    block, overflow = shared.render_agents_block(_selections(modular=HEAVY_MODULAR), budget)
    assert len(block.encode("utf-8")) <= budget
    for rule in overflow:
        assert f"<!-- rule: {rule.name} -->" not in block  # not embedded ...
        assert f"`{rule.dest}`" in block                  # ... but pointed to


def test_tight_budget_spills_templates_before_base():
    _, overflow = shared.render_agents_block(_selections(modular=HEAVY_MODULAR), 9_000)
    spilled = {r.name for r in overflow}
    assert "desktop-gui-qt.md" in spilled
    assert "coding-style.md" not in spilled


def test_heavy_selection_fits_antigravity_file_limit(tmp_path: Path):
    shared.write_agents_md(tmp_path, _selections(modular=HEAVY_MODULAR))
    # Antigravity truncates any rule file past 24,000 bytes
    assert len((tmp_path / "AGENTS.md").read_bytes()) < 24_000


# ── .agents/rules/ overflow files ──


def test_overflow_files_have_trigger_frontmatter(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(shared, "AGENTS_MD_BUDGET", 3_000)
    shared.write_agents_md(tmp_path, _selections(modular=HEAVY_MODULAR))
    python_rule = (_rules_dir(tmp_path) / "foundry-python.md").read_text()
    assert python_rule.startswith("---\ntrigger: glob\nglobs: \"**/*.py\"\n")
    template = (_rules_dir(tmp_path) / "foundry-desktop-gui-qt.md").read_text()
    assert "trigger: model_decision" in template
    assert 'description: "Desktop GUI Qt' in template
    assert shared._RULE_MARKER in template


def test_overflow_base_rule_is_always_on(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(shared, "AGENTS_MD_BUDGET", 1_500)
    shared.write_agents_md(tmp_path, _selections())
    assert "trigger: always_on" in (_rules_dir(tmp_path) / "foundry-testing.md").read_text()


def test_overflow_pruned_when_budget_allows_embedding(tmp_path: Path, monkeypatch):
    sel = _selections(modular=HEAVY_MODULAR)
    monkeypatch.setattr(shared, "AGENTS_MD_BUDGET", 3_000)
    shared.write_agents_md(tmp_path, sel)
    assert (_rules_dir(tmp_path) / "foundry-desktop-gui-qt.md").exists()
    monkeypatch.setattr(shared, "AGENTS_MD_BUDGET", 1_000_000)
    shared.write_agents_md(tmp_path, sel)
    assert not list(_rules_dir(tmp_path).glob("foundry-*.md"))


def test_prune_never_touches_unmarked_rules(tmp_path: Path, monkeypatch):
    rules = _rules_dir(tmp_path)
    rules.mkdir(parents=True)
    (rules / "python.md").write_text("project's own python rule")
    (rules / "foundry-notes.md").write_text("hand-written, no marker")
    monkeypatch.setattr(shared, "AGENTS_MD_BUDGET", 1_000_000)
    shared.write_agents_md(tmp_path, _selections())
    assert (rules / "python.md").read_text() == "project's own python rule"
    assert (rules / "foundry-notes.md").exists()


# ── .agents/skills/ ──


def test_shared_skill_has_ownership_marker(tmp_path: Path):
    shared.deploy_shared_skills(tmp_path, _selections(skills=["megamind-deep"]))
    assert (tmp_path / ".agents" / "skills" / "megamind-deep" / ".agent-foundry").is_file()


def test_unmarked_same_name_skill_left_alone(tmp_path: Path, capsys):
    # e.g. a copy Codex's Claude importer put there
    own = tmp_path / ".agents" / "skills" / "megamind-deep"
    own.mkdir(parents=True)
    (own / "SKILL.md").write_text("project copy")
    shared.deploy_shared_skills(tmp_path, _selections(skills=["megamind-deep"]))
    assert (own / "SKILL.md").read_text() == "project copy"
    assert "Left project-owned .agents/skills/megamind-deep/" in capsys.readouterr().out
    shared.deploy_shared_skills(tmp_path, _selections(skills=[]))
    assert own.is_dir()  # deselecting never deletes an unmarked dir


def test_unmarked_foundry_named_skill_not_pruned(tmp_path: Path):
    imported = tmp_path / ".agents" / "skills" / "prj-new"
    imported.mkdir(parents=True)
    shared.deploy_shared_skills(tmp_path, _selections(skills=[]))
    assert imported.is_dir()


# ── Dispatch ──


def test_deploy_shared_outputs_writes_only_what_targets_read(tmp_path: Path):
    sel = _selections(skills=["megamind-deep"], mcp_servers=["memory"])
    shared.deploy_shared_outputs(tmp_path, sel, [ClaudeAdapter()], [], {})
    assert json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["memory"]
    assert (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".agents").exists()
    shared.deploy_shared_outputs(tmp_path, sel, [CodexAdapter()], [], {})
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".agents" / "skills" / "megamind-deep").is_dir()


def test_first_run_never_removes_project_configured_servers(tmp_path: Path):
    """No recorded state, no previous selection: catalog-equal entries are the project's."""
    from foundry.deploy import selected_mcp_servers, write_mcp_servers
    catalog = selected_mcp_servers(None)
    (tmp_path / ".mcp.json").write_text(json.dumps(
        {"mcpServers": {"memory": catalog["memory"], "vercel": catalog["vercel"]}}))
    write_mcp_servers(tmp_path, [], {})
    assert set(json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]) == {
        "memory", "vercel"}


def test_upgrade_bootstraps_ownership_from_previous_selection(tmp_path: Path):
    from foundry.deploy import selected_mcp_servers
    from foundry.orchestrator import _mcp_state
    catalog = selected_mcp_servers(None)
    (tmp_path / ".mcp.json").write_text(json.dumps(
        {"mcpServers": {"memory": catalog["memory"], "railway": catalog["railway"]}}))
    state = _mcp_state({"mcp_servers": ["memory"]})  # manifest from before deployed_mcp
    from foundry.deploy import write_mcp_servers
    write_mcp_servers(tmp_path, [], state)
    servers = json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]
    assert "memory" not in servers   # the foundry wrote it (it was selected) → deselect removes
    assert "railway" in servers      # hand-added, never selected → the project's


def test_removal_never_edits_through_an_agents_md_symlink(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    header = "# p\n<!-- agent-foundry -->\nRead rules in `.claude/rules/`\n<!-- /agent-foundry -->\n"
    claude_md.write_text(header)
    (tmp_path / "AGENTS.md").symlink_to("CLAUDE.md")
    shared.remove_agents_md(tmp_path, "p")
    assert claude_md.read_text() == header
    assert (tmp_path / "AGENTS.md").is_symlink()


def test_rendered_block_has_no_claude_provenance():
    block, _ = shared.render_agents_block(_selections())
    assert "Claude Opus 4.7" not in block


def test_removing_all_shared_skills_removes_empty_root(tmp_path: Path):
    _deployed(tmp_path, "megamind-deep")
    shared.remove_shared_skills(tmp_path)
    assert not (tmp_path / ".agents" / "skills").exists()


# ── CLI-gated selection menus ──


def _record_menus(monkeypatch) -> list[str]:
    titles: list[str] = []

    def _menu(title, _items, selected, required_one=False):
        titles.append(title)
        return set(selected)

    monkeypatch.setattr("foundry.selection.toggle_menu", _menu)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    return titles


def test_copilot_only_menus_skip_claude_artifacts(tmp_path: Path, monkeypatch):
    titles = _record_menus(monkeypatch)
    consumed = CopilotAdapter().supported_artifacts()
    result = run_selection(tmp_path, None, interactive=True, cli_private_sources=None,
                           consumed=consumed)
    assert result.ok
    asked = " | ".join(titles)
    assert "Base Rules" in asked and "Skills" in asked
    for claude_only in ("Hooks", "Agents", "Plugins"):
        assert claude_only not in asked


def test_skipped_menus_keep_manifest_choices(tmp_path: Path, monkeypatch):
    _record_menus(monkeypatch)
    manifest = {"hooks": ["ruff-format.sh"], "agents": ["doc-updater.md"], "skills": []}
    result = run_selection(tmp_path, manifest, interactive=True, cli_private_sources=None,
                           consumed={"rules", "mcp", "skills"})
    # Not asked, but carried through so re-adding Claude later restores them
    assert result.hooks == ["ruff-format.sh"]
    assert result.agents == ["doc-updater.md"]


def test_all_menus_shown_without_consumed_filter(tmp_path: Path, monkeypatch):
    titles = _record_menus(monkeypatch)
    run_selection(tmp_path, None, interactive=True, cli_private_sources=None)
    asked = " | ".join(titles)
    assert "Hooks" in asked and "Agents" in asked and "Plugins" in asked


def test_private_source_step_gated_on_claude(tmp_path: Path, monkeypatch):
    prompts: list[str] = []
    _record_menus(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda msg="": prompts.append(msg) or "")
    run_selection(tmp_path, None, interactive=True, cli_private_sources=None,
                  consumed={"rules", "mcp", "skills"})
    assert not any("private config source" in p for p in prompts)


# ── Portable skills adapted for the shared root ──


def _deployed(tmp_path: Path, *skills: str) -> Path:
    shared.deploy_shared_skills(tmp_path, _selections(skills=list(skills)))
    return tmp_path / ".agents" / "skills"


@pytest.mark.parametrize("skill", sorted(PORTABLE_SKILLS))
def test_every_portable_skill_deploys_valid_and_within_codex_limit(tmp_path: Path, skill: str):
    skill_md = _deployed(tmp_path, skill) / skill / "SKILL.md"
    text = skill_md.read_text()
    meta = yaml.safe_load(text.split("---", 2)[1])
    assert meta["name"] == skill and meta["description"]
    assert not {"model", "allowed-tools"} & set(meta)       # Claude-only keys dropped
    assert len(text.encode()) <= shared._SKILL_PROMPT_LIMIT  # Codex injects ≤ 8,000 B
    for md in skill_md.parent.rglob("*.md"):
        assert ".claude/skills/" not in md.read_text(), md
        assert "Skill(" not in md.read_text(), md


def test_large_skill_split_keeps_full_text(tmp_path: Path):
    root = _deployed(tmp_path, "megamind-financial")
    stub = (root / "megamind-financial" / "SKILL.md").read_text()
    full = (root / "megamind-financial" / "SKILL.full.md").read_text()
    assert "`SKILL.full.md`" in stub
    source = (REPO_ROOT / "cli/claude/skills/megamind-financial/SKILL.md").read_text()
    assert full.split("---", 2)[2] == source.split("---", 2)[2]  # body unchanged
    assert not (root / "megamind-deep").exists()


def test_small_skill_not_split(tmp_path: Path):
    root = _deployed(tmp_path, "codex-cli")
    assert not (root / "codex-cli" / "SKILL.full.md").exists()


def test_multiline_allowed_tools_removed_cleanly(tmp_path: Path):
    skill = _deployed(tmp_path, "writer") / "writer" / "SKILL.full.md"
    meta = yaml.safe_load(skill.read_text().split("---", 2)[1])
    assert "allowed-tools" not in meta and meta["name"] == "writer"


def test_skill_invocations_rewritten(tmp_path: Path):
    text = (_deployed(tmp_path, "writer", "humanizer") / "writer" / "SKILL.full.md").read_text()
    assert "the `humanizer` skill (`.agents/skills/humanizer/SKILL.md`)" in text
    assert "one short batch of questions" in text


def test_update_foundry_portable_with_script(tmp_path: Path):
    root = _deployed(tmp_path, "update-foundry")
    skill = (root / "update-foundry" / "SKILL.md").read_text()
    assert "bash .agents/skills/update-foundry/scripts/update-foundry.sh" in skill
    script = root / "update-foundry" / "scripts" / "update-foundry.sh"
    assert os.access(script, os.X_OK)
    check = (root / "update-foundry-check" / "SKILL.md").read_text()
    assert ".agents/skills/update-foundry/scripts/update-foundry.sh --check" in check


def test_delegate_portable_with_runner(tmp_path: Path):
    root = _deployed(tmp_path, "delegate")
    skill = (root / "delegate" / "SKILL.md").read_text()
    assert "python3 .agents/skills/delegate/scripts/delegate.py" in skill
    assert os.access(root / "delegate" / "scripts" / "delegate.py", os.X_OK)


def test_local_env_files_never_deploy(tmp_path: Path, monkeypatch):
    src = tmp_path / "src" / "cli" / "claude" / "skills" / "delegate"
    shutil.copytree(REPO_ROOT / "cli" / "claude" / "skills" / "delegate", src)
    (src / "scripts" / ".env").write_text("SOME_API_KEY=maintainer-secret\n")
    (src / "scripts" / "__pycache__").mkdir()
    monkeypatch.setattr(shared, "REPO_ROOT", tmp_path / "src")
    root = _deployed(tmp_path / "proj", "delegate")
    assert not (root / "delegate" / "scripts" / ".env").exists()
    assert not (root / "delegate" / "scripts" / "__pycache__").exists()


def test_skill_subcommands_only_with_their_skill(tmp_path: Path):
    root = _deployed(tmp_path, "megamind-deep")
    assert (root / "update-codemaps").is_dir()          # standalone command
    assert not (root / "update-foundry-check").exists()  # needs update-foundry


# ── Review fixes: ownership, symlinks, encodings, policies ──


def test_copied_skill_under_new_name_survives_prune(tmp_path: Path):
    root = _deployed(tmp_path, "megamind-deep")
    shutil.copytree(root / "megamind-deep", root / "team-deep")  # marker travels along
    _deployed(tmp_path)
    assert (root / "team-deep").is_dir()
    assert not (root / "megamind-deep").exists()


# ── CLAUDE.md → AGENTS.md (Claude Code skips AGENTS.md while CLAUDE.md exists) ──

CLAUDE_HEADER = "<!-- agent-foundry -->\nRead rules in `.claude/rules/`\n<!-- /agent-foundry -->"


def test_claude_md_project_text_moves_into_agents_md(tmp_path: Path, capsys):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(f"# demo\n\n## Boundaries\nStay in demo/\n\n{CLAUDE_HEADER}\n")
    shared.write_agents_md(tmp_path, _selections(), absorb_claude_md=True)
    text = (tmp_path / "AGENTS.md").read_text()
    assert text.startswith("# demo\n\n## Boundaries\nStay in demo/\n\n<!-- agent-foundry -->\n")
    assert "<!-- rule: coding-style.md -->" in text
    assert ".claude/rules/" not in text
    assert not claude_md.exists()
    assert "Moved CLAUDE.md into AGENTS.md" in capsys.readouterr().out


def test_header_only_claude_md_is_removed(tmp_path: Path):
    (tmp_path / "CLAUDE.md").write_text(f"# demo\n\n{CLAUDE_HEADER}\n")
    shared.write_agents_md(tmp_path, _selections(), absorb_claude_md=True)
    assert (tmp_path / "AGENTS.md").read_text().startswith("# demo\n\n<!-- agent-foundry -->")
    assert not (tmp_path / "CLAUDE.md").exists()


def test_claude_md_merges_into_existing_agents_md(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text(f"# demo\n\nAgents notes\n\n{CLAUDE_HEADER}\n")
    (tmp_path / "CLAUDE.md").write_text(f"# demo\n\nClaude notes\n\n{CLAUDE_HEADER}\n")
    shared.write_agents_md(tmp_path, _selections(), absorb_claude_md=True)
    text = (tmp_path / "AGENTS.md").read_text()
    assert text.startswith("# demo\n\nAgents notes\n\nClaude notes\n\n<!-- agent-foundry -->")
    assert text.count("# demo") == 1
    assert text.count("<!-- agent-foundry -->") == 1
    assert not (tmp_path / "AGENTS.md.old").exists()


def test_claude_md_kept_when_claude_code_is_not_a_target(tmp_path: Path):
    (tmp_path / "CLAUDE.md").write_text(f"# demo\n\n{CLAUDE_HEADER}\n")
    shared.write_agents_md(tmp_path, _selections())
    assert (tmp_path / "CLAUDE.md").exists()


def test_claude_md_kept_when_agents_md_is_unreadable(tmp_path: Path):
    """CLAUDE.md goes only once AGENTS.md holds its content."""
    (tmp_path / "AGENTS.md").write_bytes("# Mine\n".encode("utf-16"))
    (tmp_path / "CLAUDE.md").write_text("# demo\n\nMine\n")
    shared.write_agents_md(tmp_path, _selections(), absorb_claude_md=True)
    assert (tmp_path / "CLAUDE.md").read_text() == "# demo\n\nMine\n"


def test_agents_md_symlinked_to_claude_md_becomes_the_file(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(f"# demo\n\nMine\n\n{CLAUDE_HEADER}\n")
    (tmp_path / "AGENTS.md").symlink_to("CLAUDE.md")
    shared.write_agents_md(tmp_path, _selections(), absorb_claude_md=True)
    agents_md = tmp_path / "AGENTS.md"
    assert not agents_md.is_symlink()
    assert agents_md.read_text().startswith("# demo\n\nMine\n\n<!-- agent-foundry -->")
    assert "<!-- rule:" in agents_md.read_text()
    assert not claude_md.exists()


def test_claude_md_symlinked_to_agents_md_is_unlinked(tmp_path: Path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text(f"# demo\n\nMine\n\n{CLAUDE_HEADER}\n")
    (tmp_path / "CLAUDE.md").symlink_to("AGENTS.md")
    shared.write_agents_md(tmp_path, _selections(), absorb_claude_md=True)
    assert not (tmp_path / "CLAUDE.md").is_symlink()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert agents_md.read_text().count("Mine") == 1
    assert "<!-- rule:" in agents_md.read_text()


def test_hard_linked_claude_md_is_unlinked(tmp_path: Path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text(f"# demo\n\nMine\n\n{CLAUDE_HEADER}\n")
    os.link(agents_md, tmp_path / "CLAUDE.md")
    shared.write_agents_md(tmp_path, _selections(), absorb_claude_md=True)
    assert not (tmp_path / "CLAUDE.md").exists()
    assert agents_md.read_text().count("Mine") == 1


def test_warns_about_files_that_hide_agents_md(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "proj"
    project.mkdir()
    (project / "CLAUDE.local.md").write_text("mine")
    shared.write_agents_md(project, _selections(), absorb_claude_md=True)
    out = capsys.readouterr().out
    assert "Claude Code skips AGENTS.md while CLAUDE.local.md exists" in out
    assert (project / "CLAUDE.local.md").exists()


# ── Block layout ──


def test_block_has_project_docs_and_nested_rule_headings(tmp_path: Path):
    block, _ = shared.render_agents_block(_selections())
    assert "### Project Docs" in block
    assert "`codemaps/INDEX.md`" in block
    # Rule H1s nest under the block's H2 instead of restarting the outline
    assert "\n### Coding Style (Core)\n" in block
    assert "\n# Coding Style" not in block


def test_demote_headings_skips_code_fences():
    body = "# Title\n## Sub\n```bash\n# a comment\n```\n~~~\n## not a heading\n~~~\n#nospace\n"
    assert shared._demote_headings(body) == (
        "### Title\n#### Sub\n```bash\n# a comment\n```\n~~~\n## not a heading\n~~~\n#nospace\n")


def test_demote_headings_caps_at_h6():
    assert shared._demote_headings("##### Deep") == "###### Deep"


def test_non_utf8_agents_md_left_alone(tmp_path: Path, capsys):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_bytes("# Mine\n".encode("utf-16"))
    shared.write_agents_md(tmp_path, _selections())
    assert agents_md.read_bytes() == "# Mine\n".encode("utf-16")
    assert "isn't UTF-8" in capsys.readouterr().out


def test_budget_floor_warns(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(shared, "AGENTS_MD_BUDGET", 500)
    shared.write_agents_md(tmp_path, _selections())
    assert "over its 500-byte budget" in capsys.readouterr().out


def test_user_only_skills_get_codex_policy(tmp_path: Path):
    root = _deployed(tmp_path, "update-foundry", "megamind-deep")
    for skill in ("update-foundry", "update-foundry-check", "update-foundry-interactive"):
        policy = root / skill / "agents" / "openai.yaml"
        assert yaml.safe_load(policy.read_text()) == {
            "policy": {"allow_implicit_invocation": False}}, skill
    assert not (root / "megamind-deep" / "agents").exists()
    assert not (root / "update-codemaps" / "agents").exists()


def test_mcp_json_reconciles_with_recorded_state(tmp_path: Path):
    state: dict = {}
    from foundry.deploy import write_mcp_servers
    write_mcp_servers(tmp_path, ["memory", "firecrawl"], state)
    path = tmp_path / ".mcp.json"
    data = json.loads(path.read_text())
    data["mcpServers"]["firecrawl"]["env"]["FIRECRAWL_API_KEY"] = "real-key"
    data["mcpServers"]["mine"] = {"command": "my-server"}
    path.write_text(json.dumps(data))
    write_mcp_servers(tmp_path, ["firecrawl"], state)
    servers = json.loads(path.read_text())["mcpServers"]
    assert servers["firecrawl"]["env"]["FIRECRAWL_API_KEY"] == "real-key"  # key kept
    assert "memory" not in servers                                          # deselected
    assert servers["mine"] == {"command": "my-server"}                      # project's own


@pytest.mark.parametrize("content", ["{}", '{"mcpServers": {}}'])
def test_projects_empty_mcp_json_survives(tmp_path: Path, content: str):
    from foundry.deploy import write_mcp_servers
    path = tmp_path / ".mcp.json"
    path.write_text(content)  # e.g. what `claude mcp remove --scope project` leaves
    write_mcp_servers(tmp_path, [], {})
    assert path.read_text() == content


def test_missing_mcp_json_clears_the_record(tmp_path: Path):
    from foundry.deploy import write_mcp_servers
    state = {".mcp.json": {"memory": None}}
    write_mcp_servers(tmp_path, [], state)
    assert state[".mcp.json"] == {}


def test_removal_skips_a_hard_linked_agents_md(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    header = "# p\n<!-- agent-foundry -->\nRead rules in `.claude/rules/`\n<!-- /agent-foundry -->\n"
    claude_md.write_text(header)
    os.link(claude_md, tmp_path / "AGENTS.md")
    shared.remove_agents_md(tmp_path, "p")
    assert claude_md.read_text() == header


def test_symlinked_skills_root_left_alone(tmp_path: Path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "skills").symlink_to(target)
    shared.remove_shared_skills(tmp_path)
    assert (tmp_path / ".agents" / "skills").is_symlink() and target.is_dir()
