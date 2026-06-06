"""Tests for CLAUDE.md handling in setup.py."""

from __future__ import annotations

import sys
from pathlib import Path

# Add tools directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from setup import (
    AGENT_FOUNDRY_MARKER_END,
    AGENT_FOUNDRY_MARKER_START,
    generate_agent_foundry_header,
    generate_claude_md,
    has_agent_foundry_header,
    prepend_agent_foundry_header,
    update_agent_foundry_header,
)


class TestHasClaudeFoundryHeader:
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


class TestGenerateClaudeFoundryHeader:
    """Tests for generate_agent_foundry_header function."""

    def test_includes_markers(self):
        header = generate_agent_foundry_header(["python.md"], {"python.md"})
        assert AGENT_FOUNDRY_MARKER_START in header
        assert AGENT_FOUNDRY_MARKER_END in header

    def test_lists_deployed_rules(self):
        rules = ["python.md", "coding-style.md", "security.md"]
        header = generate_agent_foundry_header(rules, {"python.md"})
        assert "`python.md`" in header
        assert "`coding-style.md`" in header
        assert "`security.md`" in header

    def test_includes_rule_descriptions(self):
        header = generate_agent_foundry_header(["python.md"], {"python.md"})
        assert "Python tooling" in header or "uv" in header

    def test_includes_python_env_commands(self):
        header = generate_agent_foundry_header(["python.md"], {"python.md"})
        assert "uv sync --extra dev" in header
        assert "uv run pytest" in header

    def test_includes_rust_env_commands(self):
        header = generate_agent_foundry_header(["rust.md"], {"rust.md"})
        assert "cargo build" in header
        assert "cargo test" in header

    def test_includes_go_env_commands(self):
        header = generate_agent_foundry_header(["go.md"], {"go.md"})
        assert "go mod download" in header
        assert "go test" in header

    def test_nodejs_has_no_env_commands(self):
        """Node.js has fragmented tooling — no default snippets."""
        header = generate_agent_foundry_header(["nodejs.md"], {"nodejs.md"})
        assert "npm install" not in header
        assert "npm test" not in header
        assert "No language-specific commands" in header

    def test_multiple_languages(self):
        header = generate_agent_foundry_header(
            ["python.md", "rust.md"],
            {"python.md", "rust.md"},
        )
        assert "uv" in header
        assert "cargo" in header

    def test_empty_rules_list(self):
        header = generate_agent_foundry_header([], set())
        assert AGENT_FOUNDRY_MARKER_START in header
        assert "(none deployed)" in header

    def test_no_matching_env_snippets(self):
        header = generate_agent_foundry_header(["custom-rule.md"], set())
        assert "No language-specific commands" in header

    def test_includes_architecture_section(self):
        header = generate_agent_foundry_header(["python.md"], {"python.md"})
        assert "codemaps/INDEX.md" in header
        assert "/update-codemaps" in header

    def test_includes_documentation_section(self):
        header = generate_agent_foundry_header(["python.md"], {"python.md"})
        assert "docs/" in header
        assert "docs/ARCHITECTURE.md" in header
        assert "docs/DEVELOPMENT.md" in header


class TestUpdateClaudeFoundryHeader:
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


class TestPrependClaudeFoundryHeader:
    """Tests for prepend_agent_foundry_header function."""

    def test_prepends_header(self):
        header = f"{AGENT_FOUNDRY_MARKER_START}\nheader content\n{AGENT_FOUNDRY_MARKER_END}"
        content = "# Existing Project\n\nExisting content"

        result = prepend_agent_foundry_header(content, header)

        assert result.startswith(AGENT_FOUNDRY_MARKER_START)
        assert "# Existing Project" in result
        assert "Existing content" in result

    def test_adds_newline_separator(self):
        header = f"{AGENT_FOUNDRY_MARKER_START}\nheader\n{AGENT_FOUNDRY_MARKER_END}"
        content = "# Project"

        result = prepend_agent_foundry_header(content, header)

        # Should have newline between header and content
        assert f"{AGENT_FOUNDRY_MARKER_END}\n\n# Project" in result or \
               f"{AGENT_FOUNDRY_MARKER_END}\n# Project" in result

    def test_preserves_original_content_exactly(self):
        header = "header"
        content = "line1\nline2\nline3"

        result = prepend_agent_foundry_header(content, header)

        assert "line1\nline2\nline3" in result


class TestGenerateClaudeMd:
    """Tests for generate_claude_md function."""

    def test_includes_project_name(self):
        result = generate_claude_md("my-project", ["python.md"], {"python.md"})
        assert "# my-project" in result

    def test_includes_header(self):
        result = generate_claude_md("test", ["python.md"], {"python.md"})
        assert AGENT_FOUNDRY_MARKER_START in result
        assert AGENT_FOUNDRY_MARKER_END in result

    def test_includes_deployed_rules(self):
        result = generate_claude_md(
            "test",
            ["python.md", "security.md"],
            {"python.md"},
        )
        assert "`python.md`" in result
        assert "`security.md`" in result

    def test_user_environment_section_above_marker(self):
        """New CLAUDE.md has user Environment section above the foundry marker."""
        result = generate_claude_md("test", ["python.md"], {"python.md"})
        env_pos = result.find("## Environment")
        marker_pos = result.find(AGENT_FOUNDRY_MARKER_START)
        assert env_pos < marker_pos
        assert "Add your project" in result

    def test_foundry_defaults_inside_marker(self):
        """Foundry Defaults section is inside the marker."""
        result = generate_claude_md("test", ["python.md"], {"python.md"})
        marker_start = result.find(AGENT_FOUNDRY_MARKER_START)
        marker_end = result.find(AGENT_FOUNDRY_MARKER_END)
        foundry_pos = result.find("## Foundry Defaults")
        assert marker_start < foundry_pos < marker_end


class TestContextLoad:
    """Tests for context load of different configurations.

    These tests verify that the generated CLAUDE.md content is appropriately
    sized for different project configurations.
    """

    def test_minimal_config_is_compact(self):
        """Minimal config should produce a compact CLAUDE.md."""
        result = generate_claude_md("minimal", [], set())

        # Should be under 1000 chars for minimal config
        assert len(result) < 1000
        lines = result.count("\n")
        assert lines < 40

    def test_python_only_config(self):
        """Python-only config should be reasonably sized."""
        rules = ["python.md", "coding-style.md", "testing.md"]
        result = generate_claude_md("python-project", rules, {"python.md"})

        # Should be under 2000 chars
        assert len(result) < 2000
        lines = result.count("\n")
        assert lines < 60

    def test_full_stack_config(self):
        """Full-stack config with multiple languages."""
        rules = [
            "python.md", "nodejs.md", "react.md",
            "coding-style.md", "testing.md", "security.md",
            "git-workflow.md", "architecture.md",
        ]
        langs = {"python.md", "nodejs.md", "react.md"}
        result = generate_claude_md("fullstack", rules, langs)

        # Should be under 3000 chars even with many rules
        # (includes user Environment section above marker)
        assert len(result) < 3000
        lines = result.count("\n")
        assert lines < 80

    def test_enterprise_config(self):
        """Enterprise config with all rules."""
        rules = [
            "python.md", "coding-style.md", "testing.md",
            "security.md", "enterprise.md", "git-workflow.md",
            "architecture.md", "performance.md", "agents.md",
            "codemaps.md", "hooks.md",
        ]
        result = generate_claude_md("enterprise", rules, {"python.md"})

        # Should be under 3500 chars even with all rules
        assert len(result) < 3500

    def test_header_alone_is_compact(self):
        """The header itself should be compact."""
        header = generate_agent_foundry_header(["python.md"], {"python.md"})

        # Header should be under 1000 chars
        assert len(header) < 1000
        lines = header.count("\n")
        assert lines < 35

    def test_many_rules_scales_linearly(self):
        """Adding more rules should scale linearly, not exponentially."""
        rules_5 = [f"rule{i}.md" for i in range(5)]
        rules_10 = [f"rule{i}.md" for i in range(10)]
        rules_20 = [f"rule{i}.md" for i in range(20)]

        header_5 = generate_agent_foundry_header(rules_5, set())
        header_10 = generate_agent_foundry_header(rules_10, set())
        header_20 = generate_agent_foundry_header(rules_20, set())

        # Size should roughly double when rules double
        ratio_10_5 = len(header_10) / len(header_5)
        ratio_20_10 = len(header_20) / len(header_10)

        # Allow some overhead, but should be less than 2.5x
        assert ratio_10_5 < 2.5
        assert ratio_20_10 < 2.5


class TestRulesOrdering:
    """Tests for rules ordering in header (tooling rules first)."""

    def test_language_rules_come_first(self):
        """Language rules should appear before other rules."""
        rules = ["coding-style.md", "python.md", "security.md", "rust.md"]
        header = generate_agent_foundry_header(rules, {"python.md", "rust.md"})

        # Find positions of rules in the header
        python_pos = header.find("`python.md`")
        rust_pos = header.find("`rust.md`")
        coding_pos = header.find("`coding-style.md`")
        security_pos = header.find("`security.md`")

        # Language rules should come before other rules
        assert python_pos < coding_pos
        assert python_pos < security_pos
        assert rust_pos < coding_pos
        assert rust_pos < security_pos

    def test_platform_rules_come_first(self):
        """Platform rules (github.md) should appear before non-tooling rules."""
        rules = ["coding-style.md", "github.md", "security.md"]
        header = generate_agent_foundry_header(rules, set())

        github_pos = header.find("`github.md`")
        coding_pos = header.find("`coding-style.md`")
        security_pos = header.find("`security.md`")

        # Platform rules should come before other rules
        assert github_pos < coding_pos
        assert github_pos < security_pos

    def test_tooling_rules_grouped_together(self):
        """Language and platform rules should both come before other rules."""
        rules = ["python.md", "github.md", "coding-style.md", "security.md"]
        header = generate_agent_foundry_header(rules, {"python.md"})

        python_pos = header.find("`python.md`")
        github_pos = header.find("`github.md`")
        coding_pos = header.find("`coding-style.md`")
        security_pos = header.find("`security.md`")

        # Both tooling rules should come before non-tooling rules
        assert python_pos < coding_pos
        assert github_pos < coding_pos
        assert python_pos < security_pos
        assert github_pos < security_pos

    def test_tooling_rules_sorted_alphabetically(self):
        """Tooling rules should be sorted alphabetically among themselves."""
        rules = ["rust.md", "python.md", "go.md", "github.md"]
        header = generate_agent_foundry_header(rules, {"python.md", "rust.md", "go.md"})

        github_pos = header.find("`github.md`")
        go_pos = header.find("`go.md`")
        python_pos = header.find("`python.md`")
        rust_pos = header.find("`rust.md`")

        # github < go < python < rust alphabetically
        assert github_pos < go_pos < python_pos < rust_pos

    def test_other_rules_sorted_alphabetically(self):
        """Non-tooling rules should be sorted alphabetically."""
        rules = ["testing.md", "coding-style.md", "security.md"]
        header = generate_agent_foundry_header(rules, set())

        coding_pos = header.find("`coding-style.md`")
        security_pos = header.find("`security.md`")
        testing_pos = header.find("`testing.md`")

        # coding-style < security < testing alphabetically
        assert coding_pos < security_pos < testing_pos


class TestEdgeCases:
    """Edge case tests for CLAUDE.md handling."""

    def test_unicode_content_preserved(self):
        """Unicode content should be preserved correctly."""
        header = generate_agent_foundry_header(["python.md"], {"python.md"})
        content = "# Projekt\n\nDokumentation auf Deutsch: äöü ß\n日本語テスト"

        result = prepend_agent_foundry_header(content, header)

        assert "äöü ß" in result
        assert "日本語テスト" in result

    def test_special_markdown_preserved(self):
        """Special markdown syntax should be preserved."""
        header = generate_agent_foundry_header(["python.md"], {"python.md"})
        content = """# Project

```python
def foo():
    pass
```

| Header | Value |
|--------|-------|
| A      | 1     |

> Blockquote here
"""
        result = prepend_agent_foundry_header(content, header)

        assert "```python" in result
        assert "| Header | Value |" in result
        assert "> Blockquote here" in result

    def test_empty_content_handling(self):
        """Empty content should still get header."""
        header = generate_agent_foundry_header(["python.md"], {"python.md"})
        result = prepend_agent_foundry_header("", header)

        assert AGENT_FOUNDRY_MARKER_START in result

    def test_whitespace_only_content(self):
        """Whitespace-only content should be handled."""
        header = generate_agent_foundry_header(["python.md"], {"python.md"})
        result = prepend_agent_foundry_header("   \n\n   ", header)

        assert AGENT_FOUNDRY_MARKER_START in result

    def test_existing_markdown_comments_preserved(self):
        """Existing markdown comments should not be confused with markers."""
        header = generate_agent_foundry_header(["python.md"], {"python.md"})
        content = "# Project\n\n<!-- some other comment -->\n\nContent"

        result = prepend_agent_foundry_header(content, header)

        assert "<!-- some other comment -->" in result
        assert result.count("<!--") == 3  # marker start, marker end, existing

    def test_marker_detection_exact(self):
        """Marker detection should be exact, not partial."""
        # Similar but not exact markers should not be detected
        content1 = "<!-- agent-foundry-old -->"
        content2 = "<!-- CLAUDE-FOUNDRY -->"
        content3 = "<!--agent-foundry-->"

        assert has_agent_foundry_header(content1) is False
        assert has_agent_foundry_header(content2) is False
        assert has_agent_foundry_header(content3) is False
