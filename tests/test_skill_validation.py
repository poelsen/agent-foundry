"""Tier 1: Static validation tests for all skills in the repository.

These tests run in CI and validate structural correctness of SKILL.md files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from skill_parser import ParsedSkill, discover_skills

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "cli" / "claude" / "skills"

# ── Discover all skills for parametrized tests ──

_all_skills: list[ParsedSkill] = []
if SKILLS_DIR.is_dir():
    _all_skills = discover_skills(SKILLS_DIR)

_skill_ids = [s.name for s in _all_skills]

# Skills that should have the model field set
REASONING_SKILLS = {"megamind-deep", "megamind-creative", "megamind-adversarial"}


@pytest.fixture(params=_all_skills, ids=_skill_ids)
def skill(request: pytest.FixtureRequest) -> ParsedSkill:
    """Parametrized fixture yielding each discovered skill."""
    return request.param


# ── Frontmatter validation ──


class TestFrontmatter:
    """Validate required frontmatter fields."""

    def test_has_name(self, skill: ParsedSkill):
        assert skill.name, f"{skill.path}: missing name"

    def test_has_description(self, skill: ParsedSkill):
        assert skill.description, f"{skill.path}: missing description"

    def test_name_matches_directory(self, skill: ParsedSkill):
        dir_name = skill.path.parent.name
        assert skill.name == dir_name, (
            f"{skill.path}: name '{skill.name}' does not match directory '{dir_name}'"
        )

    def test_reasoning_skills_have_model(self, skill: ParsedSkill):
        if skill.name in REASONING_SKILLS:
            assert skill.model == "opus", (
                f"{skill.path}: reasoning skill must have model: opus"
            )


# ── Structure validation ──


class TestStructure:
    """Validate SKILL.md structure."""

    def test_has_title(self, skill: ParsedSkill):
        assert skill.title, f"{skill.path}: missing H1 title"

    def test_has_body_content(self, skill: ParsedSkill):
        assert skill.body.strip(), f"{skill.path}: empty body"

    def test_no_empty_sections(self, skill: ParsedSkill):
        for heading, content in skill.sections.items():
            assert content.strip(), (
                f"{skill.path}: section '## {heading}' is empty"
            )


# ── Content bounds ──


class TestContentBounds:
    """Validate content size constraints."""

    def test_minimum_word_count(self, skill: ParsedSkill):
        assert skill.word_count >= 20, (
            f"{skill.path}: too short ({skill.word_count} words, minimum 20)"
        )

    def test_maximum_word_count(self, skill: ParsedSkill):
        assert skill.word_count <= 5000, (
            f"{skill.path}: too long ({skill.word_count} words, maximum 5000)"
        )

    def test_description_not_too_long(self, skill: ParsedSkill):
        assert len(skill.description) <= 200, (
            f"{skill.path}: description too long ({len(skill.description)} chars, max 200)"
        )


# ── Cross-reference validation ──


class TestCrossReferences:
    """Validate cross-references between skills."""

    def test_extends_target_exists(self, skill: ParsedSkill):
        if skill.extends:
            target_dir = skill.path.parent.parent / skill.extends
            assert target_dir.is_dir(), (
                f"{skill.path}: extends '{skill.extends}' but {target_dir} does not exist"
            )
            assert (target_dir / "SKILL.md").exists(), (
                f"{skill.path}: extends '{skill.extends}' but {target_dir}/SKILL.md not found"
            )

    def test_registered_in_setup(self, skill: ParsedSkill):
        """Skills should be registered in the foundry SKILLS list."""
        registry_path = REPO_ROOT / "tools" / "foundry" / "registry.py"
        if not registry_path.exists():
            pytest.skip("foundry registry not found")

        registry_content = registry_path.read_text(encoding="utf-8")
        # Check the skill name appears in the SKILLS list
        assert f'"{skill.name}"' in registry_content, (
            f"{skill.path}: skill '{skill.name}' not registered in foundry SKILLS list"
        )


# ── Registry ↔ skill-directory consistency ──


class TestRegistryConsistency:
    """Every skill named in the foundry SKILLS list must have a real SKILL.md on
    disk. A registered-but-missing skill would deploy nothing and silently break
    dependents (e.g. writer's Skill(humanizer) hand-off)."""

    def test_every_registered_skill_has_skill_md(self):
        from foundry.registry import SKILLS

        for name in SKILLS:
            skill_md = SKILLS_DIR / name / "SKILL.md"
            assert skill_md.exists(), (
                f"registry.SKILLS lists '{name}' but {skill_md} does not exist"
            )

    def test_writer_and_humanizer_registered_together(self):
        """writer invokes Skill(humanizer); both must be registered so the group
        deploys the pair together."""
        from foundry.registry import SKILLS

        if "writer" in SKILLS:
            assert "humanizer" in SKILLS, (
                "writer is registered but humanizer is not; writer's Skill(humanizer) "
                "hand-off would fail in deployed projects"
            )

    def test_skill_group_members_are_registered(self):
        """A group member missing from SKILLS would silently deploy nothing."""
        from foundry.registry import SKILL_GROUPS, SKILLS

        for group, members in SKILL_GROUPS.items():
            for name in members:
                assert name in SKILLS, (
                    f"SKILL_GROUPS[{group!r}] lists {name!r} which is not in SKILLS"
                )

    def test_writer_and_humanizer_grouped_together(self):
        """The 'Writing' group is what deploys the pair together; registration
        alone does not guarantee co-deployment."""
        from foundry.registry import SKILL_GROUPS

        writing = SKILL_GROUPS.get("Writing", [])
        assert "writer" in writing, "writer must be in SKILL_GROUPS['Writing']"
        assert "humanizer" in writing, (
            "humanizer must be in SKILL_GROUPS['Writing']; writer's Skill(humanizer) "
            "hand-off only resolves if the pair deploys together"
        )


# ── Megamind family-specific tests ──


class TestMegamindFamily:
    """Validate megamind skill family consistency."""

    def test_all_megamind_skills_exist(self):
        skill_names = {s.name for s in _all_skills}
        for name in REASONING_SKILLS:
            assert name in skill_names, f"Missing megamind skill: {name}"

    def test_megamind_deep_is_standalone(self):
        deep = next((s for s in _all_skills if s.name == "megamind-deep"), None)
        if deep is None:
            pytest.skip("megamind-deep not found")
        assert deep.extends is None

    def test_all_megamind_have_process_section(self):
        for skill in _all_skills:
            if skill.name in REASONING_SKILLS:
                assert "Process" in skill.sections, (
                    f"{skill.name}: missing ## Process section"
                )

    def test_all_megamind_have_rules_section(self):
        for skill in _all_skills:
            if skill.name in REASONING_SKILLS:
                assert "Rules" in skill.sections, (
                    f"{skill.name}: missing ## Rules section"
                )

    def test_all_megamind_require_confirmation(self):
        """All megamind skills should require user confirmation before acting."""
        for skill in _all_skills:
            if skill.name in REASONING_SKILLS:
                body_lower = skill.body.lower()
                assert "confirm" in body_lower or "stop" in body_lower, (
                    f"{skill.name}: should require confirmation before action"
                )
