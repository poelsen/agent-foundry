"""Integration tests for setup.py cmd_init: AGENTS.md as the instructions file."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add tools directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import foundry.adapters.claude as claude_adapter
from foundry.adapters.base import DeployContext
from foundry.registry import CLAUDE_ONLY_RULES
from foundry.shared import AGENTS_MD_BUDGET
from setup import (
    AGENT_FOUNDRY_MARKER_END,
    AGENT_FOUNDRY_MARKER_START,
    GoBack,
    QuitSetup,
    cmd_init,
    detect_templates,
    has_agent_foundry_header,
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


def _agents_md(project: Path) -> str:
    return (project / "AGENTS.md").read_text()


class TestNewProject:
    """Tests for initializing a new project: AGENTS.md is the instructions file."""

    def test_creates_agents_md_non_interactive(self, temp_project):
        """A new project gets AGENTS.md and no CLAUDE.md."""
        result = cmd_init(temp_project, interactive=False)

        assert result is True
        content = _agents_md(temp_project)
        assert has_agent_foundry_header(content)
        assert content.startswith("# test-project\n")
        assert not (temp_project / "CLAUDE.md").exists()

    def test_agents_md_embeds_rules(self, temp_project):
        cmd_init(temp_project, interactive=False)

        content = _agents_md(temp_project)
        assert "<!-- rule: coding-style.md -->" in content
        assert "## Coding Standards (agent-foundry)" in content

    def test_agents_md_has_environment_section(self, temp_project):
        cmd_init(temp_project, interactive=False)

        assert "### Environment" in _agents_md(temp_project)

    def test_agents_md_has_project_docs_section(self, temp_project):
        cmd_init(temp_project, interactive=False)

        content = _agents_md(temp_project)
        assert "codemaps/INDEX.md" in content
        assert "update-codemaps" in content


class TestClaudeMdMigration:
    """Claude Code reads AGENTS.md only while no CLAUDE.md exists, so an
    existing CLAUDE.md moves into AGENTS.md."""

    def test_marked_claude_md_moves_silently_non_interactive(self, temp_project):
        old_content = f"""# test-project

{AGENT_FOUNDRY_MARKER_START}
## Rules
Old rules list
{AGENT_FOUNDRY_MARKER_END}

## Custom Section
My custom content
"""
        (temp_project / "CLAUDE.md").write_text(old_content)

        result = cmd_init(temp_project, interactive=False)

        assert result is True
        content = _agents_md(temp_project)
        assert "Old rules list" not in content
        assert "## Custom Section\nMy custom content" in content
        assert content.count("# test-project") == 1
        assert not (temp_project / "CLAUDE.md").exists()
        assert not (temp_project / "CLAUDE.md.old").exists()

    def test_content_around_header_is_kept_in_order(self, temp_project):
        old_content = f"""# My Project Title

Some intro text here.

{AGENT_FOUNDRY_MARKER_START}
Old header content
{AGENT_FOUNDRY_MARKER_END}

After header
"""
        (temp_project / "CLAUDE.md").write_text(old_content)

        cmd_init(temp_project, interactive=False)

        content = _agents_md(temp_project)
        assert content.startswith("# My Project Title\n\nSome intro text here.\n\nAfter header\n\n"
                                  f"{AGENT_FOUNDRY_MARKER_START}\n")

    def test_migrates_legacy_claude_foundry_header(self, temp_project):
        """A header from before the claude-foundry rename is foundry-owned too."""
        old_content = """# test-project

## Project Boundaries
Project-owned text

<!-- claude-foundry -->
## Rules
Old rules list
<!-- /claude-foundry -->
"""
        (temp_project / "CLAUDE.md").write_text(old_content)

        result = cmd_init(temp_project, interactive=False)

        assert result is True
        content = _agents_md(temp_project)
        assert "claude-foundry" not in content
        assert "Old rules list" not in content
        assert content.count(AGENT_FOUNDRY_MARKER_START) == 1
        assert content.count(AGENT_FOUNDRY_MARKER_END) == 1
        assert content.startswith("# test-project\n\n## Project Boundaries\nProject-owned text\n")
        assert not (temp_project / "CLAUDE.md").exists()

    def test_portable_rules_leave_claude_rules_dir(self, temp_project):
        """Claude Code loads .claude/rules/ alongside AGENTS.md, so the
        portable rules live in AGENTS.md only; the Claude-only ones stay."""
        rules_dir = temp_project / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "coding-style.md").write_text("old foundry copy")
        (rules_dir / "my-team.md").write_text("project-owned")

        cmd_init(temp_project, interactive=False)

        assert not (rules_dir / "coding-style.md").exists()
        assert (rules_dir / "my-team.md").exists()
        assert {p.name for p in rules_dir.glob("*.md")} - {"my-team.md"} <= CLAUDE_ONLY_RULES
        assert (rules_dir / "agents.md").exists()


class TestExistingClaudeMdWithoutMarker:
    """A CLAUDE.md the foundry didn't write moves only with consent."""

    OLD = "# My Project\n\nExisting content without marker\n"

    def test_non_interactive_skips_without_marker(self, temp_project):
        """Non-interactive mode skips the project and writes nothing."""
        (temp_project / "CLAUDE.md").write_text(self.OLD)

        result = cmd_init(temp_project, interactive=False)

        assert result is False
        assert (temp_project / "CLAUDE.md").read_text() == self.OLD
        assert not (temp_project / "AGENTS.md").exists()
        assert not (temp_project / "CLAUDE.md.old").exists()

    def test_force_moves_after_confirmation(self, temp_project, monkeypatch):
        monkeypatch.setattr(claude_adapter, "confirm", lambda *a, **k: True)
        (temp_project / "CLAUDE.md").write_text(self.OLD)

        result = cmd_init(temp_project, interactive=False, force=True)

        assert result is True
        assert _agents_md(temp_project).startswith(
            f"# My Project\n\nExisting content without marker\n\n{AGENT_FOUNDRY_MARKER_START}\n")
        assert not (temp_project / "CLAUDE.md").exists()

    def test_force_declined_changes_nothing(self, temp_project, monkeypatch):
        monkeypatch.setattr(claude_adapter, "confirm", lambda *a, **k: False)
        (temp_project / "CLAUDE.md").write_text(self.OLD)

        assert cmd_init(temp_project, interactive=False, force=True) is False
        assert (temp_project / "CLAUDE.md").read_text() == self.OLD

    @pytest.mark.parametrize(("answer", "allowed"), [("m", True), ("", True), ("Q", False)])
    def test_interactive_move_or_quit(self, temp_project, monkeypatch, answer, allowed):
        monkeypatch.setattr("builtins.input", lambda *_: answer)
        (temp_project / "CLAUDE.md").write_text(self.OLD)
        ctx = DeployContext(interactive=True, force=False, private_prefixes=[],
                            pending_private=[], existing_private=[], cli_private_sources=[])

        assert claude_adapter._may_move_claude_md(temp_project, ctx) is allowed

    def test_empty_claude_md_is_removed(self, temp_project):
        """An empty CLAUDE.md holds nothing to lose but still hides AGENTS.md."""
        (temp_project / "CLAUDE.md").write_text("   \n\n   \n")

        assert cmd_init(temp_project, interactive=False) is True
        assert not (temp_project / "CLAUDE.md").exists()
        assert (temp_project / "AGENTS.md").exists()

    def test_non_utf8_claude_md_skips_project(self, temp_project):
        (temp_project / "CLAUDE.md").write_bytes("# Mine\n".encode("utf-16"))

        assert cmd_init(temp_project, interactive=False) is False
        assert (temp_project / "CLAUDE.md").exists()


class TestRulesInAgentsMd:
    """Tests for the rules embedded in AGENTS.md."""

    def test_python_rules_detected(self, temp_project):
        (temp_project / "pyproject.toml").write_text("[project]\nname = 'test'")

        cmd_init(temp_project, interactive=False)

        assert "<!-- rule: python.md -->" in _agents_md(temp_project)

    def test_base_rules_embedded_claude_only_rules_not(self, temp_project):
        cmd_init(temp_project, interactive=False)

        content = _agents_md(temp_project)
        assert "<!-- rule: security.md -->" in content
        assert not any(f"<!-- rule: {r} -->" in content for r in CLAUDE_ONLY_RULES)

    def test_rust_project_has_cargo_commands(self, temp_project):
        (temp_project / "Cargo.toml").write_text('[package]\nname = "test"')

        cmd_init(temp_project, interactive=False)

        assert "cargo" in _agents_md(temp_project)


class TestManifestTracking:
    """Tests for manifest and re-initialization."""

    def test_reinit_preserves_custom_content(self, temp_project):
        """Re-init keeps project content outside the foundry block."""
        cmd_init(temp_project, interactive=False)
        content = _agents_md(temp_project)
        (temp_project / "AGENTS.md").write_text(content + "\n## My Custom Section\n\nCustom stuff here\n")

        cmd_init(temp_project, interactive=False)

        new_content = _agents_md(temp_project)
        assert "## My Custom Section" in new_content
        assert "Custom stuff here" in new_content
        assert new_content.count(AGENT_FOUNDRY_MARKER_START) == 1

    def test_manifest_created(self, temp_project):
        """Manifest should be created after init."""
        cmd_init(temp_project, interactive=False)

        manifest = load_manifest(temp_project)
        assert manifest is not None
        assert "version" in manifest
        assert "base_rules" in manifest

    def test_reinit_with_manifest(self, temp_project):
        """Re-init with manifest should use saved selections."""
        cmd_init(temp_project, interactive=False)
        manifest = load_manifest(temp_project)
        manifest["base_rules"] = ["coding-style.md"]
        save_manifest(temp_project, manifest)

        cmd_init(temp_project, interactive=False)

        content = _agents_md(temp_project)
        assert "<!-- rule: coding-style.md -->" in content
        assert "<!-- rule: security.md -->" not in content


class TestContextLoadConfigurations:
    """Every rule reaches Claude Code exactly once, and AGENTS.md stays
    under the size the other CLIs read."""

    def _claude_context(self, project: Path) -> str:
        rules = sorted((project / ".claude" / "rules").glob("*.md"))
        return _agents_md(project) + "".join(r.read_text() for r in rules)

    def test_no_rule_loads_twice(self, temp_project):
        (temp_project / "pyproject.toml").write_text("[project]\nname = 'test'")

        cmd_init(temp_project, interactive=False)

        context = self._claude_context(temp_project)
        for heading in ("Coding Style (Core)", "Git Workflow", "Security Guidelines"):
            assert context.count(heading) == 1, heading

    def test_agents_md_within_budget(self, temp_project):
        (temp_project / "pyproject.toml").write_text("[project]\nname = 'test'")
        (temp_project / "Cargo.toml").write_text('[package]\nname = "test"')

        cmd_init(temp_project, interactive=False)

        assert len((temp_project / "AGENTS.md").read_bytes()) < AGENTS_MD_BUDGET + 200

    def test_multi_language_project(self, temp_project):
        (temp_project / "pyproject.toml").write_text("[project]\nname = 'test'")
        (temp_project / "Cargo.toml").write_text('[package]\nname = "test"')

        cmd_init(temp_project, interactive=False)

        content = _agents_md(temp_project)
        assert "uv sync" in content
        assert "cargo build" in content


class TestEdgeCases:
    """Edge case tests."""

    def test_unicode_in_claude_md(self, temp_project):
        old_content = f"""# Projekt

{AGENT_FOUNDRY_MARKER_START}
header
{AGENT_FOUNDRY_MARKER_END}

## Über das Projekt

日本語のドキュメント
"""
        (temp_project / "CLAUDE.md").write_text(old_content, encoding="utf-8")

        cmd_init(temp_project, interactive=False)

        new_content = (temp_project / "AGENTS.md").read_text(encoding="utf-8")
        assert "Über das Projekt" in new_content
        assert "日本語のドキュメント" in new_content

    def test_large_existing_claude_md(self, temp_project):
        large_content = f"""# Large Project

{AGENT_FOUNDRY_MARKER_START}
header
{AGENT_FOUNDRY_MARKER_END}

""" + "A" * 10000 + "\n## End"
        (temp_project / "CLAUDE.md").write_text(large_content)

        cmd_init(temp_project, interactive=False)

        new_content = _agents_md(temp_project)
        assert "## End" in new_content
        assert "A" * 10000 in new_content


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

        assert "<!-- rule: github.md -->" in _agents_md(temp_project)
        assert not (temp_project / ".claude" / "rules" / "github.md").exists()
