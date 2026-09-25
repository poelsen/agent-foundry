"""Tests for the instruction-file helpers: foundry block markers, and moving
a project's CLAUDE.md into AGENTS.md."""

from __future__ import annotations

import sys
from pathlib import Path

# Add tools directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from setup import (
    AGENT_FOUNDRY_MARKER_END,
    AGENT_FOUNDRY_MARKER_START,
    claude_md_blockers,
    has_agent_foundry_header,
    merge_project_text,
    prepend_agent_foundry_header,
    project_text,
    update_agent_foundry_header,
)

HEADER = f"{AGENT_FOUNDRY_MARKER_START}\nheader\n{AGENT_FOUNDRY_MARKER_END}"
PLACEHOLDER = f"{AGENT_FOUNDRY_MARKER_START}\n{AGENT_FOUNDRY_MARKER_END}"


class TestHasAgentFoundryHeader:
    """Tests for has_agent_foundry_header function."""

    def test_detects_marker_at_start(self):
        content = f"{AGENT_FOUNDRY_MARKER_START}\nsome content\n{AGENT_FOUNDRY_MARKER_END}"
        assert has_agent_foundry_header(content) is True

    def test_detects_marker_in_middle(self):
        content = f"# Project\n\n{AGENT_FOUNDRY_MARKER_START}\nheader\n{AGENT_FOUNDRY_MARKER_END}\n\nMore content"
        assert has_agent_foundry_header(content) is True

    def test_no_marker_returns_false(self):
        content = "# Project\n\n## Rules\nSome rules here"
        assert has_agent_foundry_header(content) is False

    def test_empty_content_returns_false(self):
        assert has_agent_foundry_header("") is False

    def test_partial_marker_returns_false(self):
        content = "<!-- claude -->\nNot the right marker"
        assert has_agent_foundry_header(content) is False

    def test_detects_legacy_claude_foundry_marker(self):
        """Headers written before the claude-foundry rename are still ours."""
        content = "# Project\n\n<!-- claude-foundry -->\nheader\n<!-- /claude-foundry -->\n"
        assert has_agent_foundry_header(content) is True

    def test_marker_detection_exact(self):
        """Similar but not exact markers are not detected."""
        assert has_agent_foundry_header("<!-- agent-foundry-old -->") is False
        assert has_agent_foundry_header("<!-- CLAUDE-FOUNDRY -->") is False
        assert has_agent_foundry_header("<!--agent-foundry-->") is False


class TestUpdateAgentFoundryHeader:
    """Tests for update_agent_foundry_header function."""

    def test_replaces_existing_header(self):
        old_header = f"{AGENT_FOUNDRY_MARKER_START}\nold content\n{AGENT_FOUNDRY_MARKER_END}"
        new_header = f"{AGENT_FOUNDRY_MARKER_START}\nnew content\n{AGENT_FOUNDRY_MARKER_END}"
        content = f"# Project\n\n{old_header}\n\n## More stuff"

        result = update_agent_foundry_header(content, new_header)

        assert "old content" not in result
        assert "new content" in result
        assert "# Project" in result
        assert "## More stuff" in result

    def test_preserves_content_before_header(self):
        old_header = f"{AGENT_FOUNDRY_MARKER_START}\nold\n{AGENT_FOUNDRY_MARKER_END}"
        new_header = f"{AGENT_FOUNDRY_MARKER_START}\nnew\n{AGENT_FOUNDRY_MARKER_END}"
        content = f"# My Project\n\nSome intro text\n\n{old_header}\n\nMore content"

        result = update_agent_foundry_header(content, new_header)

        assert result.startswith("# My Project\n\nSome intro text\n\n")

    def test_preserves_content_after_header(self):
        old_header = f"{AGENT_FOUNDRY_MARKER_START}\nold\n{AGENT_FOUNDRY_MARKER_END}"
        new_header = f"{AGENT_FOUNDRY_MARKER_START}\nnew\n{AGENT_FOUNDRY_MARKER_END}"
        content = f"{old_header}\n\n## Custom Section\n\nCustom content here"

        result = update_agent_foundry_header(content, new_header)

        assert "## Custom Section" in result
        assert "Custom content here" in result

    def test_returns_unchanged_if_no_markers(self):
        content = "# Project\n\nNo markers here"
        new_header = f"{AGENT_FOUNDRY_MARKER_START}\nnew\n{AGENT_FOUNDRY_MARKER_END}"

        result = update_agent_foundry_header(content, new_header)

        assert result == content

    def test_handles_header_at_start_of_file(self):
        old_header = f"{AGENT_FOUNDRY_MARKER_START}\nold\n{AGENT_FOUNDRY_MARKER_END}"
        new_header = f"{AGENT_FOUNDRY_MARKER_START}\nnew\n{AGENT_FOUNDRY_MARKER_END}"
        content = f"{old_header}\n\nRest of file"

        result = update_agent_foundry_header(content, new_header)

        assert result.startswith(AGENT_FOUNDRY_MARKER_START)
        assert "new" in result

    def test_replaces_legacy_claude_foundry_header(self):
        """A legacy-marked header is replaced, leaving only current markers."""
        old_header = "<!-- claude-foundry -->\nold\n<!-- /claude-foundry -->"
        new_header = f"{AGENT_FOUNDRY_MARKER_START}\nnew\n{AGENT_FOUNDRY_MARKER_END}"
        content = f"# Project\n\n{old_header}\n\nAfter"

        result = update_agent_foundry_header(content, new_header)

        assert result == f"# Project\n\n{new_header}\n\nAfter"


class TestPrependAgentFoundryHeader:
    """Tests for prepend_agent_foundry_header function."""

    def test_prepends_header(self):
        content = "# Existing Project\n\nExisting content"

        result = prepend_agent_foundry_header(content, HEADER)

        assert result.startswith(AGENT_FOUNDRY_MARKER_START)
        assert "# Existing Project" in result
        assert "Existing content" in result

    def test_adds_newline_separator(self):
        result = prepend_agent_foundry_header("# Project", HEADER)

        assert f"{AGENT_FOUNDRY_MARKER_END}\n# Project" in result

    def test_preserves_unicode_and_markdown(self):
        content = ("# Projekt\n\näöü ß 日本語\n\n```python\ndef foo():\n    pass\n```\n\n"
                   "| A | 1 |\n\n<!-- some other comment -->\n")

        result = prepend_agent_foundry_header(content, HEADER)

        assert result.endswith(content)
        assert result.count("<!--") == 3  # marker start, marker end, existing


class TestProjectText:
    """project_text: the project's own part of an instructions file."""

    def test_strips_foundry_block(self):
        content = f"# linc\n\n## Boundaries\nStay in linc/\n\n{HEADER}\n"
        assert project_text(content) == "# linc\n\n## Boundaries\nStay in linc/"

    def test_strips_legacy_block(self):
        content = "# linc\n\nMine\n\n<!-- claude-foundry -->\nold\n<!-- /claude-foundry -->\n"
        assert project_text(content) == "# linc\n\nMine"

    def test_keeps_content_on_both_sides(self):
        content = f"Before\n\n{HEADER}\n\nAfter\n"
        assert project_text(content) == "Before\n\nAfter"

    def test_unmarked_content_is_trimmed_whole(self):
        assert project_text("\n# Mine\n\nText\n\n") == "# Mine\n\nText"

    def test_header_only_is_empty(self):
        assert project_text(f"{HEADER}\n") == ""


class TestMergeProjectText:
    """merge_project_text: CLAUDE.md's project text into AGENTS.md."""

    def test_replaces_stub_title(self):
        """AGENTS.md holding only the stub title takes CLAUDE.md's text whole."""
        agents = f"# linc\n\n{HEADER}\n"
        moved = "# linc\n\n## Boundaries\nStay in linc/"

        result = merge_project_text(agents, moved, "linc")

        assert result == f"{moved}\n\n{PLACEHOLDER}\n"

    def test_marked_agents_md_keeps_its_content(self):
        agents = f"# linc\n\nAgents notes\n\n{HEADER}\n\nTail\n"

        result = merge_project_text(agents, "# linc\n\nClaude notes", "linc")

        assert result == f"# linc\n\nAgents notes\n\nClaude notes\n\n{PLACEHOLDER}\n\nTail\n"

    def test_different_titles_both_kept(self):
        agents = f"# Agents Title\n\nNotes\n\n{HEADER}\n"

        result = merge_project_text(agents, "# Claude Title\n\nMore", "linc")

        assert "# Agents Title" in result
        assert "# Claude Title\n\nMore" in result

    def test_unmarked_agents_md_gets_text_and_placeholder_appended(self):
        agents = "# Mine\n\nHand-written\n"

        result = merge_project_text(agents, "# Mine\n\nFrom Claude", "linc")

        assert result == f"# Mine\n\nHand-written\n\nFrom Claude\n\n{PLACEHOLDER}\n"


class TestClaudeMdBlockers:
    """claude_md_blockers: files that make Claude Code skip AGENTS.md."""

    def test_none_in_clean_project(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        project = tmp_path / "proj"
        project.mkdir()
        (project / "AGENTS.md").write_text("# proj\n")

        assert claude_md_blockers(project) == []

    def test_finds_project_and_ancestor_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        project = tmp_path / "repo" / "proj"
        (project / ".claude").mkdir(parents=True)
        (project / "CLAUDE.local.md").write_text("mine")
        (project / ".claude" / "CLAUDE.md").write_text("mine")
        (tmp_path / "repo" / "CLAUDE.md").write_text("parent")

        found = claude_md_blockers(project)

        assert project / "CLAUDE.local.md" in found
        assert project / ".claude" / "CLAUDE.md" in found
        assert tmp_path / "repo" / "CLAUDE.md" in found

    def test_user_memory_does_not_count(self, tmp_path, monkeypatch):
        """~/.claude/CLAUDE.md loads alongside AGENTS.md, so it's no blocker."""
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "CLAUDE.md").write_text("user memory")
        project = home / "proj"
        project.mkdir()

        assert claude_md_blockers(project) == []
