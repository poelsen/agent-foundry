"""Regression tests: deploy prunes must never delete project-owned content.

The 2026-07 thorleif incident: copy_skills()/copy_commands() deleted every
skill dir and command file they didn't recognize — including five
project-owned writer skills and two project commands — silently, with no
warning and no way to opt out. The prunes treated ".claude/ minus my
selection" as theirs to clean.

New contract for every prune pass (rules, agents, commands, skills):

1. Delete only names that are provably foundry-owned — present in the
   current catalog (registry + shipped files) or explicitly listed as
   retired (RETIRED_* in registry.py, MANIFEST_MIGRATION for rules).
2. Print every deletion, so no removal is ever silent.
3. Leave everything else in place and report it, so the user can see what
   the foundry deliberately did not touch.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from setup import copy_agents, copy_commands, copy_rules, copy_skills  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    p = tmp_path / "project"
    for subdir in ["rules", "agents", "commands", "skills"]:
        (p / ".claude" / subdir).mkdir(parents=True)
    return p


# ── Skills ────────────────────────────────────────────────────────────


class TestProjectOwnedSkills:
    # The five skills the thorleif update deleted.
    PROJECT_SKILLS: ClassVar[list[str]] = [
        "portfolio-update", "sector-thesis-commentary", "stock-investment-case",
        "stock-quarterly-update", "stock-short-note",
    ]

    def test_project_skills_survive_prune(self, project: Path):
        """The exact incident scenario: project-owned skill dirs that the
        foundry never shipped must survive a deploy with any selection."""
        skills_dir = project / ".claude" / "skills"
        for name in self.PROJECT_SKILLS:
            (skills_dir / name).mkdir()
            (skills_dir / name / "SKILL.md").write_text("# project-owned\n", encoding="utf-8")

        copy_skills(project, ["megamind-deep"])

        for name in self.PROJECT_SKILLS:
            assert (skills_dir / name / "SKILL.md").is_file(), (
                f"project-owned skill {name} was deleted by the foundry prune"
            )
        assert (skills_dir / "megamind-deep").is_dir()

    def test_stale_foundry_skill_still_removed(self, project: Path):
        """A deselected skill from the foundry catalog is still cleaned up."""
        stale = project / ".claude" / "skills" / "clickhouse-io"
        stale.mkdir()
        (stale / "SKILL.md").write_text("stale foundry skill", encoding="utf-8")

        copy_skills(project, ["megamind-deep"])

        assert not stale.exists()

    def test_deletion_is_reported(self, project: Path, capsys):
        stale = project / ".claude" / "skills" / "clickhouse-io"
        stale.mkdir()
        (stale / "SKILL.md").write_text("stale", encoding="utf-8")

        copy_skills(project, [])

        assert "clickhouse-io" in capsys.readouterr().out, (
            "removals must be printed — silent deletion is the original bug"
        )

    def test_kept_project_skills_are_reported(self, project: Path, capsys):
        skills_dir = project / ".claude" / "skills"
        (skills_dir / "portfolio-update").mkdir()
        (skills_dir / "portfolio-update" / "SKILL.md").write_text("x", encoding="utf-8")

        copy_skills(project, [])

        assert "portfolio-update" in capsys.readouterr().out

    def test_private_and_protected_dirs_not_reported_as_foreign(self, project: Path, capsys):
        """learned/, _lib/, and private-prefixed dirs are foundry-managed —
        they are neither removed nor listed as non-foundry leftovers."""
        skills_dir = project / ".claude" / "skills"
        for name in ["learned", "_lib", "company-tool"]:
            (skills_dir / name).mkdir()

        copy_skills(project, [], private_prefixes=["company"])

        out = capsys.readouterr().out
        assert "company-tool" not in out
        assert (skills_dir / "learned").is_dir()
        assert (skills_dir / "_lib").is_dir()  # rebuilt from source, still present
        assert (skills_dir / "company-tool").is_dir()


# ── Commands ──────────────────────────────────────────────────────────


class TestProjectOwnedCommands:
    def test_project_commands_survive_prune(self, project: Path):
        """The incident's second casualty: /stocks-refresh + /stocks-refresh-fmp."""
        cmd_dir = project / ".claude" / "commands"
        (cmd_dir / "stocks-refresh.md").write_text("# project command\n", encoding="utf-8")
        (cmd_dir / "stocks-refresh-fmp.md").write_text("# project command\n", encoding="utf-8")

        copy_commands(project, [])

        assert (cmd_dir / "stocks-refresh.md").is_file()
        assert (cmd_dir / "stocks-refresh-fmp.md").is_file()

    def test_stale_foundry_command_still_removed(self, project: Path):
        """A catalog command whose parent skill is deselected is cleaned up."""
        cmd_dir = project / ".claude" / "commands"
        (cmd_dir / "update-foundry-check.md").write_text("stale", encoding="utf-8")

        copy_commands(project, [])  # update-foundry not selected

        assert not (cmd_dir / "update-foundry-check.md").exists()

    def test_retired_wrapper_still_removed(self, project: Path):
        """Wrappers named exactly after a skill no longer ship at all, but
        stem ∈ SKILLS proves foundry ownership — still pruned."""
        cmd_dir = project / ".claude" / "commands"
        (cmd_dir / "megamind-deep.md").write_text("old wrapper", encoding="utf-8")

        copy_commands(project, ["megamind-deep"])

        assert not (cmd_dir / "megamind-deep.md").exists()

    def test_retired_command_removed(self, project: Path):
        """/recall shipped until it became the learn-recall skill; listed in
        RETIRED_COMMANDS, so old projects still get it cleaned out."""
        cmd_dir = project / ".claude" / "commands"
        (cmd_dir / "recall.md").write_text("# /recall - Search Learned Skills\n", encoding="utf-8")

        copy_commands(project, [])

        assert not (cmd_dir / "recall.md").exists()

    def test_command_prune_is_reported(self, project: Path, capsys):
        cmd_dir = project / ".claude" / "commands"
        (cmd_dir / "update-foundry-check.md").write_text("stale", encoding="utf-8")
        (cmd_dir / "stocks-refresh.md").write_text("mine", encoding="utf-8")

        copy_commands(project, [])

        out = capsys.readouterr().out
        assert "update-foundry-check.md" in out  # deletion printed
        assert "stocks-refresh.md" in out  # kept file reported


# ── Rules ─────────────────────────────────────────────────────────────


class TestProjectOwnedRules:
    def test_project_rule_survives_prune(self, project: Path):
        rules_dir = project / ".claude" / "rules"
        (rules_dir / "my-project-conventions.md").write_text("# mine\n", encoding="utf-8")

        copy_rules(project, base=["security.md"], modular={})

        assert (rules_dir / "my-project-conventions.md").is_file()
        assert (rules_dir / "security.md").is_file()

    def test_retired_rule_names_still_removed(self, project: Path):
        """Old names recorded in MANIFEST_MIGRATION (issue #25) stay cleanable,
        in both flat and category-prefixed deployed forms."""
        rules_dir = project / ".claude" / "rules"
        (rules_dir / "gui.md").write_text("stale", encoding="utf-8")
        (rules_dir / "lang-python-qt.md").write_text("stale", encoding="utf-8")

        copy_rules(project, base=["security.md"], modular={})

        assert not (rules_dir / "gui.md").exists()
        assert not (rules_dir / "lang-python-qt.md").exists()

    def test_catalog_readme_is_not_treated_as_foundry_rule(self, project: Path):
        """common/rules/README.md documents the catalog and is never deployed —
        a project's own README.md in .claude/rules/ must not be deleted."""
        rules_dir = project / ".claude" / "rules"
        (rules_dir / "README.md").write_text("# my notes\n", encoding="utf-8")

        copy_rules(project, base=["security.md"], modular={})

        assert (rules_dir / "README.md").is_file()


# ── Agents ────────────────────────────────────────────────────────────


class TestProjectOwnedAgents:
    def test_project_agent_survives_prune(self, project: Path):
        agents_dir = project / ".claude" / "agents"
        (agents_dir / "my-domain-expert.md").write_text("# mine\n", encoding="utf-8")

        copy_agents(project, ["tdd-guide-python.md"])

        assert (agents_dir / "my-domain-expert.md").is_file()
        assert (agents_dir / "tdd-guide-python.md").is_file()

    def test_stale_foundry_agent_still_removed(self, project: Path):
        agents_dir = project / ".claude" / "agents"
        (agents_dir / "doc-updater.md").write_text("stale", encoding="utf-8")

        copy_agents(project, [])

        assert not (agents_dir / "doc-updater.md").exists()
