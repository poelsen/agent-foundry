"""Tests for private source features in setup.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add tools directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from setup import (
    clean_private_files,
    copy_agents,
    copy_commands,
    copy_skills,
    deploy_private_source,
    discover_private_content,
    redeploy_private_sources,
    validate_prefix,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path):
    """Create a temporary project with .claude/ structure."""
    p = tmp_path / "project"
    p.mkdir()
    for subdir in ["rules", "agents", "commands", "skills", "hooks/library"]:
        (p / ".claude" / subdir).mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def private_source(tmp_path):
    """Create a temporary private source directory."""
    src = tmp_path / "company-config"
    # Rules
    (src / "rule-library" / "lang").mkdir(parents=True)
    (src / "rule-library" / "lang" / "custom-dsp.md").write_text("# DSP rules\n")
    (src / "rule-library" / "lang" / "custom-mcu.md").write_text("# MCU rules\n")
    # Commands
    (src / "commands").mkdir()
    (src / "commands" / "deploy.md").write_text("# Deploy command\n")
    # Skills
    (src / "skills" / "custom-tool").mkdir(parents=True)
    (src / "skills" / "custom-tool" / "SKILL.md").write_text("# Custom tool skill\n")
    # Agents
    (src / "agents").mkdir()
    (src / "agents" / "custom-reviewer.md").write_text("# Custom reviewer\n")
    # Hooks
    (src / "hooks" / "library").mkdir(parents=True)
    (src / "hooks" / "library" / "custom-lint.sh").write_text("#!/bin/bash\necho lint\n")
    return src


# ── validate_prefix ──────────────────────────────────────────────────


class TestValidatePrefix:
    def test_valid_prefix(self):
        assert validate_prefix("company", []) is None

    def test_valid_prefix_with_hyphens(self):
        assert validate_prefix("my-team", []) is None

    def test_valid_prefix_with_numbers(self):
        assert validate_prefix("team42", []) is None

    def test_rejects_uppercase(self):
        err = validate_prefix("Company", [])
        assert err is not None
        assert "lowercase" in err

    def test_rejects_starting_with_number(self):
        err = validate_prefix("42team", [])
        assert err is not None

    def test_rejects_special_chars(self):
        err = validate_prefix("my_team", [])
        assert err is not None

    def test_rejects_reserved_prefix(self):
        err = validate_prefix("security", [])
        assert err is not None
        assert "conflicts" in err

    def test_rejects_reserved_category(self):
        err = validate_prefix("lang", [])
        assert err is not None
        assert "conflicts" in err

    def test_rejects_duplicate(self):
        err = validate_prefix("company", ["company"])
        assert err is not None
        assert "already registered" in err

    def test_allows_non_duplicate(self):
        assert validate_prefix("company", ["team"]) is None


# ── discover_private_content ─────────────────────────────────────────


class TestDiscoverPrivateContent:
    def test_discovers_all_components(self, private_source):
        content = discover_private_content(private_source)
        assert "lang/custom-dsp.md" in content["rules"]
        assert "lang/custom-mcu.md" in content["rules"]
        assert "deploy.md" in content["commands"]
        assert "custom-tool" in content["skills"]
        assert "custom-reviewer.md" in content["agents"]
        assert "custom-lint.sh" in content["hooks"]

    def test_empty_directory(self, tmp_path):
        src = tmp_path / "empty"
        src.mkdir()
        content = discover_private_content(src)
        assert all(len(v) == 0 for v in content.values())

    def test_partial_structure(self, tmp_path):
        src = tmp_path / "partial"
        (src / "rule-library" / "lang").mkdir(parents=True)
        (src / "rule-library" / "lang" / "foo.md").write_text("# Foo\n")
        content = discover_private_content(src)
        assert len(content["rules"]) == 1
        assert len(content["commands"]) == 0


# ── clean_private_files ──────────────────────────────────────────────


class TestCleanPrivateFiles:
    def test_removes_prefixed_rules(self, project):
        rules_dir = project / ".claude" / "rules"
        (rules_dir / "company-dsp.md").write_text("old")
        (rules_dir / "company-mcu.md").write_text("old")
        (rules_dir / "python.md").write_text("keep")

        clean_private_files(project, "company")

        assert not (rules_dir / "company-dsp.md").exists()
        assert not (rules_dir / "company-mcu.md").exists()
        assert (rules_dir / "python.md").exists()

    def test_removes_prefixed_agents(self, project):
        agents_dir = project / ".claude" / "agents"
        (agents_dir / "company-reviewer.md").write_text("old")
        (agents_dir / "tdd-guide-python.md").write_text("keep")

        clean_private_files(project, "company")

        assert not (agents_dir / "company-reviewer.md").exists()
        assert (agents_dir / "tdd-guide-python.md").exists()

    def test_removes_prefixed_skill_dirs(self, project):
        skills_dir = project / ".claude" / "skills"
        (skills_dir / "company-tool").mkdir()
        (skills_dir / "company-tool" / "SKILL.md").write_text("old")
        (skills_dir / "megamind-deep").mkdir()

        clean_private_files(project, "company")

        assert not (skills_dir / "company-tool").exists()
        assert (skills_dir / "megamind-deep").exists()

    def test_removes_prefixed_hooks(self, project):
        hooks_dir = project / ".claude" / "hooks" / "library"
        (hooks_dir / "company-lint.sh").write_text("old")
        (hooks_dir / "ruff-format.sh").write_text("keep")

        clean_private_files(project, "company")

        assert not (hooks_dir / "company-lint.sh").exists()
        assert (hooks_dir / "ruff-format.sh").exists()

    def test_does_not_touch_other_prefix(self, project):
        rules_dir = project / ".claude" / "rules"
        (rules_dir / "team-foo.md").write_text("keep")

        clean_private_files(project, "company")

        assert (rules_dir / "team-foo.md").exists()

    def test_handles_missing_dirs(self, tmp_path):
        """Should not crash if .claude subdirs don't exist."""
        project = tmp_path / "bare"
        project.mkdir()
        (project / ".claude").mkdir()
        clean_private_files(project, "company")  # Should not raise


# ── deploy_private_source ────────────────────────────────────────────


class TestDeployPrivateSource:
    def test_deploys_rules_with_prefix(self, project, private_source):
        selections = {"rules": ["lang/custom-dsp.md"], "commands": [], "skills": [], "agents": [], "hooks": []}
        deployed = deploy_private_source(project, private_source, "company", selections)

        assert (project / ".claude" / "rules" / "company-custom-dsp.md").exists()
        assert "lang/custom-dsp.md" in deployed["rules"]

    def test_deploys_commands_with_prefix(self, project, private_source):
        selections = {"rules": [], "commands": ["deploy.md"], "skills": [], "agents": [], "hooks": []}
        deployed = deploy_private_source(project, private_source, "company", selections)

        assert (project / ".claude" / "commands" / "company-deploy.md").exists()
        assert "deploy.md" in deployed["commands"]

    def test_deploys_skills_with_prefix(self, project, private_source):
        selections = {"rules": [], "commands": [], "skills": ["custom-tool"], "agents": [], "hooks": []}
        deployed = deploy_private_source(project, private_source, "company", selections)

        skill_dir = project / ".claude" / "skills" / "company-custom-tool"
        assert skill_dir.is_dir()
        assert (skill_dir / "SKILL.md").exists()
        assert "custom-tool" in deployed["skills"]

    def test_deploys_agents_with_prefix(self, project, private_source):
        selections = {"rules": [], "commands": [], "skills": [], "agents": ["custom-reviewer.md"], "hooks": []}
        deploy_private_source(project, private_source, "company", selections)

        assert (project / ".claude" / "agents" / "company-custom-reviewer.md").exists()

    def test_deploys_hooks_with_prefix(self, project, private_source):
        selections = {"rules": [], "commands": [], "skills": [], "agents": [], "hooks": ["custom-lint.sh"]}
        deploy_private_source(project, private_source, "company", selections)

        hook = project / ".claude" / "hooks" / "library" / "company-custom-lint.sh"
        assert hook.exists()
        assert hook.stat().st_mode & 0o111  # Executable

    def test_deploys_all_components(self, project, private_source):
        selections = {
            "rules": ["lang/custom-dsp.md", "lang/custom-mcu.md"],
            "commands": ["deploy.md"],
            "skills": ["custom-tool"],
            "agents": ["custom-reviewer.md"],
            "hooks": ["custom-lint.sh"],
        }
        deployed = deploy_private_source(project, private_source, "company", selections)

        assert len(deployed["rules"]) == 2
        assert len(deployed["commands"]) == 1
        assert len(deployed["skills"]) == 1
        assert len(deployed["agents"]) == 1
        assert len(deployed["hooks"]) == 1

    def test_skips_missing_source_files(self, project, private_source):
        selections = {"rules": ["lang/nonexistent.md"], "commands": [], "skills": [], "agents": [], "hooks": []}
        deployed = deploy_private_source(project, private_source, "company", selections)

        assert len(deployed["rules"]) == 0


# ── redeploy_private_sources ─────────────────────────────────────────


class TestRedeployPrivateSources:
    def test_redeploys_from_manifest(self, project, private_source):
        sources = [{
            "path": str(private_source),
            "prefix": "company",
            "rules": ["lang/custom-dsp.md"],
            "commands": [],
            "skills": [],
            "agents": [],
            "hooks": [],
        }]
        result = redeploy_private_sources(project, sources)

        assert len(result) == 1
        assert (project / ".claude" / "rules" / "company-custom-dsp.md").exists()

    def test_cleans_old_files_before_redeploy(self, project, private_source):
        # Pre-populate with old file that's no longer selected
        (project / ".claude" / "rules" / "company-old-rule.md").write_text("stale")

        sources = [{
            "path": str(private_source),
            "prefix": "company",
            "rules": ["lang/custom-dsp.md"],
            "commands": [],
            "skills": [],
            "agents": [],
            "hooks": [],
        }]
        redeploy_private_sources(project, sources)

        assert not (project / ".claude" / "rules" / "company-old-rule.md").exists()
        assert (project / ".claude" / "rules" / "company-custom-dsp.md").exists()

    def test_handles_missing_source_path(self, project, tmp_path):
        sources = [{
            "path": str(tmp_path / "nonexistent"),
            "prefix": "company",
            "rules": ["lang/foo.md"],
            "commands": [],
            "skills": [],
            "agents": [],
            "hooks": [],
        }]
        result = redeploy_private_sources(project, sources)

        # Should keep source in manifest but not crash
        assert len(result) == 1


# ── copy_skills cleanup ─────────────────────────────────────────────


class TestCopySkillsCleanup:
    def test_removes_deselected_skills(self, project, tmp_path):
        # Simulate a skill that was previously deployed
        old_skill = project / ".claude" / "skills" / "old-skill"
        old_skill.mkdir(parents=True)
        (old_skill / "SKILL.md").write_text("old")

        # copy_skills with empty list should remove old-skill
        copy_skills(project, [])

        assert not old_skill.exists()

    def test_preserves_learned_directory(self, project, tmp_path):
        learned = project / ".claude" / "skills" / "learned"
        learned.mkdir(parents=True)
        (learned / "python").mkdir()
        (learned / "python" / "pattern.md").write_text("keep")

        copy_skills(project, [])

        assert learned.exists()
        assert (learned / "python" / "pattern.md").exists()

    def test_preserves_learned_local_directory(self, project, tmp_path):
        local = project / ".claude" / "skills" / "learned-local"
        local.mkdir(parents=True)
        (local / "my-pattern.md").write_text("keep")

        copy_skills(project, [])

        assert local.exists()

    def test_preserves_private_prefixed_skills(self, project, tmp_path):
        private_skill = project / ".claude" / "skills" / "company-tool"
        private_skill.mkdir(parents=True)
        (private_skill / "SKILL.md").write_text("keep")

        copy_skills(project, [], private_prefixes=["company"])

        assert private_skill.exists()

    def test_removes_non_private_non_protected(self, project, tmp_path):
        # Old foundry skill (not in current selection, not protected)
        stale = project / ".claude" / "skills" / "some-old-foundry-skill"
        stale.mkdir(parents=True)
        (stale / "SKILL.md").write_text("stale")

        # Private skill (should survive)
        private = project / ".claude" / "skills" / "company-tool"
        private.mkdir(parents=True)
        (private / "SKILL.md").write_text("keep")

        copy_skills(project, [], private_prefixes=["company"])

        assert not stale.exists()
        assert private.exists()


# ── copy_agents prefix awareness ─────────────────────────────────────


class TestCopyAgentsPrefixAwareness:
    def test_skips_private_agents_during_cleanup(self, project, tmp_path):
        agents_dir = project / ".claude" / "agents"
        (agents_dir / "company-reviewer.md").write_text("private")
        (agents_dir / "stale-agent.md").write_text("stale")

        copy_agents(project, [], private_prefixes=["company"])

        assert (agents_dir / "company-reviewer.md").exists()
        assert not (agents_dir / "stale-agent.md").exists()


# ── copy_commands prefix awareness ───────────────────────────────────


class TestCopyCommandsPrefixAwareness:
    def test_skips_private_commands_during_cleanup(self, project, tmp_path):
        cmd_dir = project / ".claude" / "commands"
        (cmd_dir / "company-deploy.md").write_text("private")
        (cmd_dir / "stale-command.md").write_text("stale")

        copy_commands(project, [], private_prefixes=["company"])

        assert (cmd_dir / "company-deploy.md").exists()
        assert not (cmd_dir / "stale-command.md").exists()
