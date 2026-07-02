"""Tests for skill_parser.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from skill_parser import (
    discover_skills,
    extract_sections,
    extract_title,
    parse_frontmatter,
    parse_skill,
)


class TestParseFrontmatter:
    """Tests for YAML frontmatter extraction."""

    def test_basic_frontmatter(self):
        content = "---\nname: test\ndescription: A test\n---\n\n# Body"
        fm, body = parse_frontmatter(content)
        assert fm["name"] == "test"
        assert fm["description"] == "A test"
        assert "# Body" in body

    def test_frontmatter_with_model(self):
        content = "---\nname: test\ndescription: desc\nmodel: opus\n---\n\nBody"
        fm, _ = parse_frontmatter(content)
        assert fm["model"] == "opus"

    def test_frontmatter_with_extends(self):
        content = "---\nname: child\ndescription: desc\nextends: parent\n---\n\nBody"
        fm, _ = parse_frontmatter(content)
        assert fm["extends"] == "parent"

    def test_no_frontmatter(self):
        content = "# Just a heading\n\nSome body text"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_empty_content(self):
        fm, body = parse_frontmatter("")
        assert fm == {}
        assert body == ""

    def test_unquoted_colon_in_description_raises(self):
        """Claude Code parses frontmatter with a spec-compliant YAML parser, which
        rejects an unquoted 'key: value' colon inside a plain scalar. The foundry
        parser must reject it too, or CI validates skills that fail to deploy."""
        content = "---\nname: test\ndescription: A test: with colons: everywhere\n---\n\nBody"
        with pytest.raises(ValueError, match="Invalid YAML frontmatter"):
            parse_frontmatter(content)

    def test_quoted_description_with_colons(self):
        content = '---\nname: test\ndescription: "A test: with colons: everywhere"\n---\n\nBody'
        fm, _ = parse_frontmatter(content)
        assert fm["description"] == "A test: with colons: everywhere"

    def test_block_scalar_description(self):
        content = "---\nname: test\ndescription: |\n  Line one.\n  Line two.\n---\n\nBody"
        fm, _ = parse_frontmatter(content)
        assert fm["description"] == "Line one.\nLine two."


class TestExtractSections:
    """Tests for markdown section extraction."""

    def test_basic_sections(self):
        body = "## Process\n\nStep 1\nStep 2\n\n## Rules\n\nRule 1"
        sections = extract_sections(body)
        assert "Process" in sections
        assert "Rules" in sections
        assert "Step 1" in sections["Process"]
        assert "Rule 1" in sections["Rules"]

    def test_no_sections(self):
        body = "Just plain text\nwith no headings"
        sections = extract_sections(body)
        assert sections == {}

    def test_ignores_h1_and_h3(self):
        body = "# Title\n\n### Subsection\n\n## Real Section\n\nContent"
        sections = extract_sections(body)
        assert "Real Section" in sections
        assert "Title" not in sections
        assert "Subsection" not in sections

    def test_empty_section(self):
        body = "## Empty\n\n## HasContent\n\nStuff here"
        sections = extract_sections(body)
        assert sections["Empty"] == ""
        assert "Stuff here" in sections["HasContent"]


class TestExtractTitle:
    """Tests for H1 title extraction."""

    def test_basic_title(self):
        assert extract_title("# My Skill\n\nBody") == "My Skill"

    def test_title_after_blank_lines(self):
        assert extract_title("\n\n# My Skill\n\nBody") == "My Skill"

    def test_no_title(self):
        assert extract_title("No heading here") == ""

    def test_h2_not_title(self):
        assert extract_title("## Not a title") == ""


class TestParseSkill:
    """Tests for full skill parsing."""

    def test_parse_valid_skill(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: megamind\ndescription: Think deeply\nmodel: opus\n---\n\n"
            "# Megamind\n\nIntro text\n\n## Process\n\nStep 1\n\n## Rules\n\nRule 1\n"
        )

        skill = parse_skill(skill_file)

        assert skill.name == "megamind"
        assert skill.description == "Think deeply"
        assert skill.model == "opus"
        assert skill.title == "Megamind"
        assert "Process" in skill.sections
        assert "Rules" in skill.sections
        assert skill.word_count > 0
        assert skill.path == skill_file

    def test_parse_with_extends(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: child\ndescription: Child skill\nextends: parent\n---\n\n# Child\n"
        )

        skill = parse_skill(skill_file)
        assert skill.extends == "parent"

    def test_missing_name_raises(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\ndescription: no name\n---\n\n# Oops\n")

        with pytest.raises(ValueError, match="Missing required frontmatter field 'name'"):
            parse_skill(skill_file)

    def test_missing_description_raises(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\nname: test\n---\n\n# Test\n")

        with pytest.raises(ValueError, match="Missing required frontmatter field 'description'"):
            parse_skill(skill_file)

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_skill(tmp_path / "nonexistent.md")

    def test_frozen_dataclass(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\nname: test\ndescription: Test\n---\n\n# Test\n")

        skill = parse_skill(skill_file)
        with pytest.raises(AttributeError):
            skill.name = "changed"  # type: ignore[misc]


class TestDiscoverSkills:
    """Tests for skill discovery."""

    def test_discovers_skills(self, tmp_path):
        for name in ("alpha", "beta"):
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Skill {name}\n---\n\n# {name.title()}\n"
            )

        skills = discover_skills(tmp_path)
        assert len(skills) == 2
        assert skills[0].name == "alpha"
        assert skills[1].name == "beta"

    def test_skips_learned_directories(self, tmp_path):
        for name in ("learned", "learned-local", "real-skill"):
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Skill {name}\n---\n\n# {name}\n"
            )

        skills = discover_skills(tmp_path)
        assert len(skills) == 1
        assert skills[0].name == "real-skill"

    def test_skips_directories_without_skill_md(self, tmp_path):
        (tmp_path / "has-skill").mkdir()
        (tmp_path / "has-skill" / "SKILL.md").write_text(
            "---\nname: has-skill\ndescription: Yes\n---\n\n# Has\n"
        )
        (tmp_path / "no-skill").mkdir()
        (tmp_path / "no-skill" / "README.md").write_text("Not a skill")

        skills = discover_skills(tmp_path)
        assert len(skills) == 1

    def test_nonexistent_directory(self, tmp_path):
        skills = discover_skills(tmp_path / "nope")
        assert skills == []
