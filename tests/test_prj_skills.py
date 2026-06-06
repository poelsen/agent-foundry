"""Tests for prj-* project management skills and scripts."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "cli" / "claude" / "skills"


def _install_skills(tmp_path: Path) -> None:
    """Copy prj-* skills + _lib into tmp_path/.claude/skills/ so PROJECT_ROOT resolves."""
    dest_skills = tmp_path / ".claude" / "skills"
    dest_skills.mkdir(parents=True, exist_ok=True)
    # Copy _lib
    shutil.copytree(SKILLS_DIR / "_lib", dest_skills / "_lib")
    # Copy each prj-* skill
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.name.startswith("prj-") and skill_dir.is_dir():
            shutil.copytree(skill_dir, dest_skills / skill_dir.name)


def _script_path(tmp_path: Path, skill: str, script: str) -> Path:
    """Return path to an installed script inside tmp_path."""
    return tmp_path / ".claude" / "skills" / skill / "scripts" / script


# ── Skill structure validation ──


class TestPrjSkillStructure:
    """Verify all prj-* skills have the required files."""

    PRJ_SKILLS = ["prj-new", "prj-list", "prj-pause", "prj-resume", "prj-done", "prj-delete"]

    @pytest.mark.parametrize("skill", PRJ_SKILLS)
    def test_skill_has_skill_md(self, skill: str):
        skill_md = SKILLS_DIR / skill / "SKILL.md"
        assert skill_md.exists(), f"{skill}/SKILL.md not found"

    @pytest.mark.parametrize("skill", PRJ_SKILLS)
    def test_skill_md_has_frontmatter(self, skill: str):
        content = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
        assert content.startswith("---"), f"{skill}/SKILL.md missing YAML frontmatter"
        assert f"name: {skill}" in content, f"{skill}/SKILL.md frontmatter missing name"

    @pytest.mark.parametrize(
        "skill",
        ["prj-new", "prj-list", "prj-pause", "prj-done", "prj-delete"],
    )
    def test_script_skills_have_scripts(self, skill: str):
        scripts_dir = SKILLS_DIR / skill / "scripts"
        assert scripts_dir.is_dir(), f"{skill}/scripts/ not found"
        scripts = list(scripts_dir.glob("*.sh"))
        assert len(scripts) >= 1, f"{skill}/scripts/ has no .sh files"

    def test_prj_resume_is_model_only(self):
        """prj-resume is model-only — verify SKILL.md exists (scripts dir is optional)."""
        skill_md = SKILLS_DIR / "prj-resume" / "SKILL.md"
        assert skill_md.exists(), "prj-resume/SKILL.md not found"

    def test_shared_lib_exists(self):
        lib = SKILLS_DIR / "_lib" / "session-id.sh"
        assert lib.exists(), "skills/_lib/session-id.sh not found"


# ── Command file validation ──


class TestPrjCommandFiles:
    """Verify command files exist and reference correct skills."""

    COMMANDS_DIR = REPO_ROOT / "cli" / "claude" / "commands"
    PRJ_COMMANDS = ["prj-new", "prj-list", "prj-pause", "prj-resume", "prj-done", "prj-delete"]

    @pytest.mark.parametrize("cmd", PRJ_COMMANDS)
    def test_command_file_exists(self, cmd: str):
        cmd_file = self.COMMANDS_DIR / f"{cmd}.md"
        assert cmd_file.exists(), f"commands/{cmd}.md not found"

    @pytest.mark.parametrize("cmd", PRJ_COMMANDS)
    def test_command_references_skill(self, cmd: str):
        content = (self.COMMANDS_DIR / f"{cmd}.md").read_text(encoding="utf-8")
        assert f".claude/skills/{cmd}/SKILL.md" in content, (
            f"commands/{cmd}.md doesn't reference the skill"
        )


# ── Script functional tests ──


class TestPrjNewScript:
    """Test the prj-new.sh script."""

    def _run_script(self, tmp_path: Path, name: str) -> subprocess.CompletedProcess:
        _install_skills(tmp_path)
        script = _script_path(tmp_path, "prj-new", "prj-new.sh")
        return subprocess.run(
            ["bash", str(script), name],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "HOME": str(tmp_path)},
        )

    def test_creates_project_file(self, tmp_path: Path):
        result = self._run_script(tmp_path, "test-project")
        assert result.returncode == 0, result.stderr
        prj_file = tmp_path / ".claude" / "prjs" / "test-project.md"
        assert prj_file.exists()

    def test_project_file_has_frontmatter(self, tmp_path: Path):
        self._run_script(tmp_path, "my-project")
        content = (tmp_path / ".claude" / "prjs" / "my-project.md").read_text()
        assert "name: my-project" in content
        assert "status: active" in content

    def test_project_file_has_sections(self, tmp_path: Path):
        self._run_script(tmp_path, "my-project")
        content = (tmp_path / ".claude" / "prjs" / "my-project.md").read_text()
        for section in ["## Goal", "## Status", "## Decisions", "## Key Files", "## Resume"]:
            assert section in content, f"Missing section: {section}"

    def test_rejects_duplicate(self, tmp_path: Path):
        self._run_script(tmp_path, "dupe")
        # Re-install since first call already set up the structure
        result = subprocess.run(
            ["bash", str(_script_path(tmp_path, "prj-new", "prj-new.sh")), "dupe"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "HOME": str(tmp_path)},
        )
        assert result.returncode != 0
        assert "already exists" in result.stdout

    def test_rejects_invalid_name(self, tmp_path: Path):
        result = self._run_script(tmp_path, "Bad Name!")
        assert result.returncode != 0

    def test_rejects_empty_name(self, tmp_path: Path):
        result = self._run_script(tmp_path, "")
        assert result.returncode != 0


class TestPrjListScript:
    """Test the prj-list.sh script."""

    def _run_script(self, tmp_path: Path) -> subprocess.CompletedProcess:
        _install_skills(tmp_path)
        script = _script_path(tmp_path, "prj-list", "prj-list.sh")
        return subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

    def test_empty_project_list(self, tmp_path: Path):
        result = self._run_script(tmp_path)
        assert result.returncode == 0
        assert "No projects found" in result.stdout

    def test_lists_existing_projects(self, tmp_path: Path):
        _install_skills(tmp_path)
        prjs_dir = tmp_path / ".claude" / "prjs"
        prjs_dir.mkdir(parents=True, exist_ok=True)
        (prjs_dir / "alpha.md").write_text(
            "---\nname: alpha\nstatus: active\nupdated: 2026-01-01\nsession_id: abc123\n---\n"
        )
        (prjs_dir / "beta.md").write_text(
            "---\nname: beta\nstatus: paused\nupdated: 2026-01-02\nsession_id: def456\n---\n"
        )
        script = _script_path(tmp_path, "prj-list", "prj-list.sh")
        result = subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert "alpha" in result.stdout
        assert "beta" in result.stdout
        assert "2 project(s)" in result.stdout


class TestPrjDoneScript:
    """Test the prj-done.sh script."""

    def _run_script(self, tmp_path: Path, name: str) -> subprocess.CompletedProcess:
        _install_skills(tmp_path)
        script = _script_path(tmp_path, "prj-done", "prj-done.sh")
        return subprocess.run(
            ["bash", str(script), name],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

    def test_marks_project_done(self, tmp_path: Path):
        _install_skills(tmp_path)
        prjs_dir = tmp_path / ".claude" / "prjs"
        prjs_dir.mkdir(parents=True, exist_ok=True)
        prj_file = prjs_dir / "myprj.md"
        prj_file.write_text(
            "---\nname: myprj\nstatus: active\nupdated: 2026-01-01\n---\n"
        )
        script = _script_path(tmp_path, "prj-done", "prj-done.sh")
        result = subprocess.run(
            ["bash", str(script), "myprj"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        content = prj_file.read_text()
        assert "status: done" in content

    def test_nonexistent_project(self, tmp_path: Path):
        result = self._run_script(tmp_path, "nope")
        assert result.returncode != 0
        assert "not found" in result.stdout


class TestPrjDeleteScript:
    """Test the prj-delete.sh script."""

    def _run_script(self, tmp_path: Path, name: str) -> subprocess.CompletedProcess:
        _install_skills(tmp_path)
        script = _script_path(tmp_path, "prj-delete", "prj-delete.sh")
        return subprocess.run(
            ["bash", str(script), name],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

    def test_deletes_project(self, tmp_path: Path):
        _install_skills(tmp_path)
        prjs_dir = tmp_path / ".claude" / "prjs"
        prjs_dir.mkdir(parents=True, exist_ok=True)
        prj_file = prjs_dir / "deleteme.md"
        prj_file.write_text("---\nname: deleteme\nstatus: active\n---\n")
        script = _script_path(tmp_path, "prj-delete", "prj-delete.sh")
        result = subprocess.run(
            ["bash", str(script), "deleteme"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert not prj_file.exists()

    def test_nonexistent_project(self, tmp_path: Path):
        result = self._run_script(tmp_path, "nope")
        assert result.returncode != 0


class TestPrjPauseScript:
    """Test the prj-pause.sh script."""

    def _run_script(self, tmp_path: Path, name: str) -> subprocess.CompletedProcess:
        _install_skills(tmp_path)
        script = _script_path(tmp_path, "prj-pause", "prj-pause.sh")
        return subprocess.run(
            ["bash", str(script), name],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "HOME": str(tmp_path)},
        )

    def test_pauses_existing_project(self, tmp_path: Path):
        _install_skills(tmp_path)
        prjs_dir = tmp_path / ".claude" / "prjs"
        prjs_dir.mkdir(parents=True, exist_ok=True)
        prj_file = prjs_dir / "myprj.md"
        prj_file.write_text(
            "---\nname: myprj\nstatus: active\nupdated: 2026-01-01\nsession_id: old123\n---\n"
        )
        script = _script_path(tmp_path, "prj-pause", "prj-pause.sh")
        result = subprocess.run(
            ["bash", str(script), "myprj"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "HOME": str(tmp_path)},
        )
        assert result.returncode == 0, result.stderr
        content = prj_file.read_text()
        assert "status: paused" in content

    def test_nonexistent_project_fails(self, tmp_path: Path):
        result = self._run_script(tmp_path, "nope")
        assert result.returncode != 0
        assert "not found" in result.stdout


# ── Session ID detection ──


class TestSessionIdLib:
    """Test the shared session-id.sh library."""

    def test_session_id_defaults_to_unknown(self, tmp_path: Path):
        """With no .claude/projects dir, SESSION_ID should be 'unknown'."""
        script = f"""
source {SKILLS_DIR / '_lib' / 'session-id.sh'}
echo "SESSION_ID=$SESSION_ID"
echo "SHORT_ID=$SHORT_ID"
"""
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "HOME": str(tmp_path)},
        )
        assert "SESSION_ID=unknown" in result.stdout
        assert "SHORT_ID=unknown" in result.stdout


# ── Setup.py registration ──


class TestPrjSetupRegistration:
    """Verify prj-* skills are registered in setup.py."""

    def test_skills_registered(self):
        setup_content = (REPO_ROOT / "tools" / "setup.py").read_text(encoding="utf-8")
        for skill in ["prj-new", "prj-list", "prj-pause", "prj-resume", "prj-done", "prj-delete"]:
            assert f'"{skill}"' in setup_content, f"{skill} not registered in setup.py SKILLS"

    def test_lib_copy_in_setup(self):
        setup_content = (REPO_ROOT / "tools" / "setup.py").read_text(encoding="utf-8")
        assert "_lib" in setup_content, "setup.py doesn't copy _lib/ directory"
