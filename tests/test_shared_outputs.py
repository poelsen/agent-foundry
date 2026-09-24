"""Tests for outputs shared across CLIs (foundry/shared.py) and CLI-gated selection."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import pytest
import yaml

from foundry import shared
from foundry.adapters import CopilotAdapter, Selections
from foundry.adapters.base import AGENTS_MD, AGENTS_SKILLS, MCP_JSON
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
        "mcp_servers": [], "features": [], "langs": {"python.md"},
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


def test_deploy_shared_outputs_writes_only_requested(tmp_path: Path):
    sel = _selections(skills=["megamind-deep"], mcp_servers=["memory"])
    shared.deploy_shared_outputs(tmp_path, sel, {MCP_JSON})
    assert json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["memory"]
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".agents").exists()
    shared.deploy_shared_outputs(tmp_path, sel, {AGENTS_MD, AGENTS_SKILLS})
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".agents" / "skills" / "megamind-deep").is_dir()


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


def test_skill_subcommands_only_with_their_skill(tmp_path: Path):
    root = _deployed(tmp_path, "megamind-deep")
    assert (root / "update-codemaps").is_dir()          # standalone command
    assert not (root / "update-foundry-check").exists()  # needs update-foundry
