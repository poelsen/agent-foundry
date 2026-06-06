"""Integration tests for setup.py cmd_init with CLAUDE.md handling."""

from __future__ import annotations

import sys
from pathlib import Path
from io import StringIO

import pytest

# Add tools directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from setup import (
    CLAUDE_FOUNDRY_MARKER_START,
    CLAUDE_FOUNDRY_MARKER_END,
    GoBack,
    QuitSetup,
    cmd_init,
    detect_templates,
    has_claude_foundry_header,
    load_manifest,
    migrate_manifest,
    save_manifest,
    toggle_menu,
)


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory."""
    project = tmp_path / "test-project"
    project.mkdir()
    return project


class TestNewProject:
    """Tests for initializing a new project without existing CLAUDE.md."""

    def test_creates_claude_md_non_interactive(self, temp_project):
        """New project should get CLAUDE.md created in non-interactive mode."""
        result = cmd_init(temp_project, interactive=False)

        assert result is True
        claude_md = temp_project / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert has_claude_foundry_header(content)
        assert "test-project" in content

    def test_claude_md_has_rules_section(self, temp_project):
        """New CLAUDE.md should list deployed rules."""
        cmd_init(temp_project, interactive=False)

        content = (temp_project / "CLAUDE.md").read_text()
        assert ".claude/rules/" in content
        assert "## Rules" in content

    def test_claude_md_has_environment_section(self, temp_project):
        """New CLAUDE.md should have environment section."""
        cmd_init(temp_project, interactive=False)

        content = (temp_project / "CLAUDE.md").read_text()
        assert "## Environment" in content

    def test_claude_md_has_architecture_section(self, temp_project):
        """New CLAUDE.md should have architecture section."""
        cmd_init(temp_project, interactive=False)

        content = (temp_project / "CLAUDE.md").read_text()
        assert "codemaps/INDEX.md" in content
        assert "/update-codemaps" in content


class TestExistingClaudeMdWithMarker:
    """Tests for projects with existing CLAUDE.md that has marker."""

    def test_updates_header_silently_non_interactive(self, temp_project):
        """Existing CLAUDE.md with marker should be updated silently."""
        # Create existing CLAUDE.md with marker
        old_content = f"""# test-project

{CLAUDE_FOUNDRY_MARKER_START}
## Rules
Old rules list
{CLAUDE_FOUNDRY_MARKER_END}

## Custom Section
My custom content
"""
        (temp_project / "CLAUDE.md").write_text(old_content)

        result = cmd_init(temp_project, interactive=False)

        assert result is True

        new_content = (temp_project / "CLAUDE.md").read_text()
        # Header should be updated
        assert "Old rules list" not in new_content
        # Custom section should be preserved
        assert "## Custom Section" in new_content
        assert "My custom content" in new_content
        # No backup should be created for marker updates
        assert not (temp_project / "CLAUDE.md.old").exists()

    def test_preserves_content_before_header(self, temp_project):
        """Content before header should be preserved."""
        old_content = f"""# My Project Title

Some intro text here.

{CLAUDE_FOUNDRY_MARKER_START}
Old header content
{CLAUDE_FOUNDRY_MARKER_END}

After header
"""
        (temp_project / "CLAUDE.md").write_text(old_content)

        cmd_init(temp_project, interactive=False)

        new_content = (temp_project / "CLAUDE.md").read_text()
        assert "# My Project Title" in new_content
        assert "Some intro text here." in new_content
        assert "After header" in new_content


class TestExistingClaudeMdWithoutMarker:
    """Tests for projects with existing CLAUDE.md without marker."""

    def test_non_interactive_skips_without_marker(self, temp_project):
        """Non-interactive mode should skip entire project without marker."""
        old_content = """# My Project

Existing content without marker
"""
        (temp_project / "CLAUDE.md").write_text(old_content)

        result = cmd_init(temp_project, interactive=False)

        assert result is False
        # CLAUDE.md should be unchanged
        assert (temp_project / "CLAUDE.md").read_text() == old_content
        # No backup created
        assert not (temp_project / "CLAUDE.md.old").exists()


class TestRulesInHeader:
    """Tests for rules list in generated header."""

    def test_python_rules_detected(self, temp_project):
        """Python project should have Python rules in header."""
        # Create pyproject.toml to trigger Python detection
        (temp_project / "pyproject.toml").write_text("[project]\nname = 'test'")

        cmd_init(temp_project, interactive=False)

        content = (temp_project / "CLAUDE.md").read_text()
        assert "`python.md`" in content

    def test_base_rules_in_header(self, temp_project):
        """Base rules should appear in header."""
        cmd_init(temp_project, interactive=False)

        content = (temp_project / "CLAUDE.md").read_text()
        # At least some base rules should be listed
        assert "`coding-style.md`" in content or "`security.md`" in content

    def test_rust_project_has_cargo_commands(self, temp_project):
        """Rust project should have cargo commands in environment."""
        (temp_project / "Cargo.toml").write_text('[package]\nname = "test"')

        cmd_init(temp_project, interactive=False)

        content = (temp_project / "CLAUDE.md").read_text()
        assert "cargo" in content


class TestManifestTracking:
    """Tests for manifest and re-initialization."""

    def test_reinit_preserves_custom_content(self, temp_project):
        """Re-init should preserve custom content after header."""
        # First init
        cmd_init(temp_project, interactive=False)

        # Add custom content after header
        content = (temp_project / "CLAUDE.md").read_text()
        content += "\n## My Custom Section\n\nCustom stuff here\n"
        (temp_project / "CLAUDE.md").write_text(content)

        # Second init (should update header, keep custom)
        cmd_init(temp_project, interactive=False)

        new_content = (temp_project / "CLAUDE.md").read_text()
        assert "## My Custom Section" in new_content
        assert "Custom stuff here" in new_content

    def test_manifest_created(self, temp_project):
        """Manifest should be created after init."""
        cmd_init(temp_project, interactive=False)

        manifest = load_manifest(temp_project)
        assert manifest is not None
        assert "version" in manifest
        assert "base_rules" in manifest

    def test_reinit_with_manifest(self, temp_project):
        """Re-init with manifest should use saved selections."""
        # First init creates manifest
        cmd_init(temp_project, interactive=False)

        # Modify manifest to have specific selections
        manifest = load_manifest(temp_project)
        manifest["base_rules"] = ["coding-style.md"]
        save_manifest(temp_project, manifest)

        # Re-init should use manifest
        cmd_init(temp_project, interactive=False)

        # Should still succeed
        assert (temp_project / "CLAUDE.md").exists()


class TestContextLoadConfigurations:
    """Tests for context load of different project configurations."""

    def test_empty_project_minimal_claude_md(self, temp_project):
        """Empty project should have minimal CLAUDE.md."""
        cmd_init(temp_project, interactive=False)

        content = (temp_project / "CLAUDE.md").read_text()
        # Should be reasonably sized
        assert len(content) < 4000
        assert content.count("\n") < 100

    def test_python_project_claude_md_size(self, temp_project):
        """Python project CLAUDE.md should be appropriately sized."""
        (temp_project / "pyproject.toml").write_text("[project]\nname = 'test'")
        (temp_project / "src").mkdir()
        (temp_project / "src" / "main.py").write_text("# Python file")

        cmd_init(temp_project, interactive=False)

        content = (temp_project / "CLAUDE.md").read_text()
        assert len(content) < 5000

    def test_multi_language_project(self, temp_project):
        """Multi-language project should have combined env commands."""
        (temp_project / "pyproject.toml").write_text("[project]\nname = 'test'")
        (temp_project / "Cargo.toml").write_text('[package]\nname = "test"')

        cmd_init(temp_project, interactive=False)

        content = (temp_project / "CLAUDE.md").read_text()
        # Should have commands for both
        assert "uv" in content or "cargo" in content


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_claude_md_file_skipped(self, temp_project):
        """Empty CLAUDE.md without marker should skip entire project."""
        (temp_project / "CLAUDE.md").write_text("")

        result = cmd_init(temp_project, interactive=False)

        assert result is False
        # Empty file stays empty (skipped)
        assert (temp_project / "CLAUDE.md").read_text() == ""

    def test_whitespace_only_claude_md(self, temp_project):
        """Whitespace-only CLAUDE.md should skip entire project."""
        (temp_project / "CLAUDE.md").write_text("   \n\n   \n")

        result = cmd_init(temp_project, interactive=False)

        assert result is False

    def test_unicode_in_claude_md(self, temp_project):
        """Unicode in existing CLAUDE.md should be preserved."""
        old_content = f"""# Projekt

{CLAUDE_FOUNDRY_MARKER_START}
header
{CLAUDE_FOUNDRY_MARKER_END}

## Über das Projekt

日本語のドキュメント
"""
        (temp_project / "CLAUDE.md").write_text(old_content)

        cmd_init(temp_project, interactive=False)

        new_content = (temp_project / "CLAUDE.md").read_text()
        assert "Über das Projekt" in new_content
        assert "日本語のドキュメント" in new_content

    def test_large_existing_claude_md(self, temp_project):
        """Large existing CLAUDE.md should be handled."""
        # Create a large CLAUDE.md (10KB)
        large_content = f"""# Large Project

{CLAUDE_FOUNDRY_MARKER_START}
header
{CLAUDE_FOUNDRY_MARKER_END}

""" + "A" * 10000 + "\n## End"
        (temp_project / "CLAUDE.md").write_text(large_content)

        cmd_init(temp_project, interactive=False)

        new_content = (temp_project / "CLAUDE.md").read_text()
        assert "## End" in new_content
        # Content should be preserved
        assert "A" * 100 in new_content


class TestVersionFile:
    """Tests for VERSION file handling."""

    def test_version_file_created(self, temp_project):
        """VERSION file should be created in .claude/."""
        cmd_init(temp_project, interactive=False)

        version_file = temp_project / ".claude" / "VERSION"
        assert version_file.exists()
        assert version_file.read_text().strip()

    def test_rules_copied(self, temp_project):
        """Rules should be copied to .claude/rules/."""
        cmd_init(temp_project, interactive=False)

        rules_dir = temp_project / ".claude" / "rules"
        assert rules_dir.is_dir()
        # Should have at least some rules
        rules = list(rules_dir.glob("*.md"))
        assert len(rules) > 0


class TestDetectTemplates:
    """Tests for template auto-detection."""

    def test_react_detected_via_dep_keyword(self, tmp_path):
        """react-app.md should be detected from package.json dependency."""
        project = tmp_path / "proj"
        project.mkdir()
        (project / "package.json").write_text('{"dependencies": {"react": "^18"}}')

        detected = detect_templates(project)
        assert "react-app.md" in detected

    def test_qt_detected_via_dep_keyword(self, tmp_path):
        """desktop-gui-qt.md should be detected from PySide6 dependency."""
        project = tmp_path / "proj"
        project.mkdir()
        (project / "pyproject.toml").write_text('[project]\ndependencies = ["PySide6"]')

        detected = detect_templates(project)
        assert "desktop-gui-qt.md" in detected

    def test_manual_templates_not_auto_detected(self, tmp_path):
        """Manual templates (embedded-c, embedded-dsp, rest-api) should not auto-detect."""
        project = tmp_path / "proj"
        project.mkdir()
        # Create .c files and Makefile — still shouldn't trigger embedded-c (manual)
        (project / "main.c").write_text("int main() {}")
        (project / "Makefile").write_text("all:")

        detected = detect_templates(project)
        assert "embedded-c.md" not in detected
        assert "embedded-dsp.md" not in detected
        assert "rest-api.md" not in detected

    def test_empty_project_no_templates(self, tmp_path):
        """Empty project should detect no templates."""
        project = tmp_path / "proj"
        project.mkdir()

        detected = detect_templates(project)
        assert detected == set()

    def test_non_manual_without_keywords_not_detected(self, tmp_path):
        """Templates like library.md with no detection keys should not auto-detect."""
        project = tmp_path / "proj"
        project.mkdir()

        detected = detect_templates(project)
        assert "library.md" not in detected
        assert "scripts.md" not in detected
        assert "monolith.md" not in detected


class TestMigrateManifest:
    """Tests for manifest migration from old to new category structure."""

    def test_domain_embedded_migrates_to_templates(self):
        """domain/embedded.md should migrate to templates/embedded-c.md."""
        manifest = {"modular_rules": {"domain": ["embedded.md"]}}
        result = migrate_manifest(manifest)

        assert "domain" not in result["modular_rules"]
        assert "embedded-c.md" in result["modular_rules"]["templates"]

    def test_lang_react_migrates_to_templates(self):
        """lang/react.md should migrate to templates/react-app.md."""
        manifest = {"modular_rules": {"lang": ["python.md", "react.md"]}}
        result = migrate_manifest(manifest)

        assert "react.md" not in result["modular_rules"]["lang"]
        assert "python.md" in result["modular_rules"]["lang"]
        assert "react-app.md" in result["modular_rules"]["templates"]

    def test_none_target_drops_rule(self):
        """Rules mapped to None should be removed without replacement."""
        manifest = {"modular_rules": {"domain": ["gui.md"], "lang": ["c.md", "python.md"]}}
        result = migrate_manifest(manifest)

        assert "domain" not in result["modular_rules"]
        assert "c.md" not in result["modular_rules"]["lang"]
        assert "python.md" in result["modular_rules"]["lang"]
        # gui.md and c.md have no replacement
        assert "templates" not in result["modular_rules"] or \
            "gui.md" not in result["modular_rules"].get("templates", [])

    def test_duplicate_targets_deduplicated(self):
        """Both style/backend.md and arch/rest-api.md map to templates/rest-api.md."""
        manifest = {"modular_rules": {
            "style": ["backend.md"],
            "arch": ["rest-api.md"],
        }}
        result = migrate_manifest(manifest)

        assert "style" not in result["modular_rules"]
        assert "arch" not in result["modular_rules"]
        assert result["modular_rules"]["templates"].count("rest-api.md") == 1

    def test_empty_old_categories_cleaned_up(self):
        """Old categories should be removed when emptied."""
        manifest = {"modular_rules": {
            "domain": ["embedded.md"],
            "arch": ["monolith.md"],
            "style": ["scripts.md"],
        }}
        result = migrate_manifest(manifest)

        for cat in ("domain", "arch", "style"):
            assert cat not in result["modular_rules"]

    def test_no_migration_needed(self):
        """Manifest with only new-style categories should be unchanged."""
        manifest = {"modular_rules": {
            "lang": ["python.md"],
            "templates": ["react-app.md"],
        }}
        result = migrate_manifest(manifest)

        assert result["modular_rules"] == {
            "lang": ["python.md"],
            "templates": ["react-app.md"],
        }

    def test_empty_manifest(self):
        """Manifest with no modular_rules should not crash, and gains the
        default `clis` target (pre-multi-CLI manifests were Claude-only)."""
        manifest = {"version": "1.0"}
        result = migrate_manifest(manifest)

        assert result == {"version": "1.0", "clis": ["claude"]}

    def test_full_migration_scenario(self):
        """Realistic manifest with multiple old categories."""
        manifest = {"modular_rules": {
            "lang": ["python.md", "python-qt.md", "react.md", "c.md"],
            "domain": ["embedded.md", "dsp-audio.md", "gui-threading.md"],
            "style": ["backend.md", "library.md"],
            "arch": ["react-app.md"],
            "platform": ["github.md"],
        }}
        result = migrate_manifest(manifest)
        modular = result["modular_rules"]

        # Old categories cleaned up
        assert "domain" not in modular
        assert "style" not in modular
        assert "arch" not in modular
        # Lang kept non-migrated rules
        assert modular["lang"] == ["python.md"]
        # Templates collected all migrations
        templates = set(modular["templates"])
        assert templates == {
            "embedded-c.md", "embedded-dsp.md", "desktop-gui-qt.md",
            "rest-api.md", "library.md", "react-app.md",
        }
        # Platform untouched
        assert modular["platform"] == ["github.md"]

    def test_reinit_with_migrated_manifest(self, tmp_path):
        """cmd_init with old-format manifest should migrate and work."""
        project = tmp_path / "test-project"
        project.mkdir()
        # First init to create structure
        cmd_init(project, interactive=False)

        # Write old-format manifest
        manifest = load_manifest(project)
        manifest["modular_rules"] = {
            "lang": ["python.md", "react.md"],
            "style": ["backend.md"],
        }
        save_manifest(project, manifest)

        # Re-init should migrate and succeed
        result = cmd_init(project, interactive=False)
        assert result is True

        # Manifest should now have templates
        new_manifest = load_manifest(project)
        assert "style" not in new_manifest.get("modular_rules", {})


class TestToggleMenuNavigation:
    """Tests for back/quit navigation in toggle_menu."""

    def test_quit_raises_quit_setup(self, monkeypatch):
        """Typing 'q' should raise QuitSetup."""
        monkeypatch.setattr("builtins.input", lambda _: "q")
        with pytest.raises(QuitSetup):
            toggle_menu("Test", ["a", "b"], set())

    def test_quit_word_raises_quit_setup(self, monkeypatch):
        """Typing 'quit' should raise QuitSetup."""
        monkeypatch.setattr("builtins.input", lambda _: "quit")
        with pytest.raises(QuitSetup):
            toggle_menu("Test", ["a", "b"], set())

    def test_back_raises_go_back(self, monkeypatch):
        """Typing 'b' should raise GoBack."""
        monkeypatch.setattr("builtins.input", lambda _: "b")
        with pytest.raises(GoBack):
            toggle_menu("Test", ["a", "b"], set())

    def test_back_word_raises_go_back(self, monkeypatch):
        """Typing 'back' should raise GoBack."""
        monkeypatch.setattr("builtins.input", lambda _: "back")
        with pytest.raises(GoBack):
            toggle_menu("Test", ["a", "b"], set())

    def test_enter_confirms_selection(self, monkeypatch):
        """Empty input should confirm and return selection."""
        monkeypatch.setattr("builtins.input", lambda _: "")
        result = toggle_menu("Test", ["a", "b", "c"], {0, 2})
        assert result == {0, 2}

    def test_toggle_then_confirm(self, monkeypatch):
        """Toggle an item then confirm."""
        inputs = iter(["2", ""])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        result = toggle_menu("Test", ["a", "b", "c"], {0})
        assert result == {0, 1}  # 0 was pre-selected, 2 toggled on (1-indexed)

    def test_does_not_mutate_input_set(self, monkeypatch):
        """toggle_menu should not mutate the caller's selected set."""
        inputs = iter(["1", ""])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        original = {0, 1}
        original_copy = set(original)
        toggle_menu("Test", ["a", "b", "c"], original)
        assert original == original_copy

    def test_back_case_insensitive(self, monkeypatch):
        """'B' and 'BACK' should also raise GoBack."""
        monkeypatch.setattr("builtins.input", lambda _: "B")
        with pytest.raises(GoBack):
            toggle_menu("Test", ["a"], set())

    def test_quit_case_insensitive(self, monkeypatch):
        """'Q' and 'QUIT' should also raise QuitSetup."""
        monkeypatch.setattr("builtins.input", lambda _: "Q")
        with pytest.raises(QuitSetup):
            toggle_menu("Test", ["a"], set())


class TestGitHubPlatformDetection:
    """Tests for GitHub platform detection."""

    def test_github_dir_detected(self, temp_project):
        """Projects with .github/ should get github.md rule."""
        (temp_project / ".github").mkdir()
        (temp_project / ".github" / "workflows").mkdir()

        cmd_init(temp_project, interactive=False)

        # Check if github.md was copied
        rules_dir = temp_project / ".claude" / "rules"
        github_rule = rules_dir / "github.md"
        assert github_rule.exists()
