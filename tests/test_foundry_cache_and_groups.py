"""Tests for per-project foundry payload and skill grouping.

Covers:
- SKILL_GROUPS shape + default contents
- HIDDEN_SKILLS is well-formed (empty today; no skills are menu-hidden)
- _install_foundry_payload writes setup.py + foundry.tar.gz to <project>/.foundry/
- Payload install is idempotent and skips when REPO_ROOT lives inside target
- Migrates away from legacy <project>/.claude/foundry/ exploded tree
"""

from __future__ import annotations

import shutil
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import setup as setup_py  # noqa: E402


class TestSkillGroupsShape:
    """Verify SKILL_GROUPS constant is well-formed and matches the rest of setup.py."""

    def test_groups_dict_exists(self):
        assert hasattr(setup_py, "SKILL_GROUPS")
        assert isinstance(setup_py.SKILL_GROUPS, dict)

    def test_groups_have_expected_names(self):
        assert "Megamind Reasoning" in setup_py.SKILL_GROUPS
        assert "Project Management" in setup_py.SKILL_GROUPS

    def test_megamind_group_contains_all_4_skills(self):
        members = setup_py.SKILL_GROUPS["Megamind Reasoning"]
        assert set(members) == {
            "megamind-deep", "megamind-creative", "megamind-adversarial", "megamind-financial",
        }

    def test_prj_group_contains_all_6_skills(self):
        members = setup_py.SKILL_GROUPS["Project Management"]
        assert set(members) == {
            "prj-new", "prj-list", "prj-pause", "prj-resume", "prj-done", "prj-delete",
        }

    def test_copilot_is_not_a_group(self):
        """Copilot CLI is a single reference skill, never a group."""
        assert "Copilot MCP" not in setup_py.SKILL_GROUPS
        assert "Copilot" not in setup_py.SKILL_GROUPS

    def test_all_group_members_are_in_SKILLS(self):
        for group, members in setup_py.SKILL_GROUPS.items():
            for skill in members:
                assert skill in setup_py.SKILLS, (
                    f"group '{group}' references unknown skill '{skill}'"
                )


class TestHiddenSkills:
    """HIDDEN_SKILLS is kept as an explicit set so the menu-build logic
    stays uniform. No skills are menu-hidden today (the copilot-* MCP skills
    that used to live here were retired with the VS Code bridge)."""

    def test_hidden_skills_exists(self):
        assert hasattr(setup_py, "HIDDEN_SKILLS")
        assert isinstance(setup_py.HIDDEN_SKILLS, set)

    def test_hidden_skills_is_empty(self):
        assert setup_py.HIDDEN_SKILLS == set()

    def test_no_copilot_mcp_skill_constant(self):
        """The COPILOT_SKILLS gating list was removed; nothing should
        reintroduce a menu-hidden copilot skill set by accident."""
        assert not hasattr(setup_py, "COPILOT_SKILLS")


class TestFoundryPayloadInstall:
    """Verify _install_foundry_payload writes the .foundry/ payload correctly."""

    def test_writes_tarball_and_setup_py(self, tmp_path: Path):
        setup_py._install_foundry_payload(tmp_path)
        foundry_dir = tmp_path / ".foundry"
        assert foundry_dir.is_dir()
        assert (foundry_dir / "setup.py").is_file()
        assert (foundry_dir / "foundry.tar.gz").is_file()

    def test_setup_py_matches_running_script(self, tmp_path: Path):
        """The deployed setup.py must be a copy of the canonical tools/setup.py."""
        setup_py._install_foundry_payload(tmp_path)
        deployed = (tmp_path / ".foundry" / "setup.py").read_bytes()
        canonical = (REPO_ROOT / "tools" / "setup.py").read_bytes()
        assert deployed == canonical

    def test_tarball_contains_setup_py_and_skills(self, tmp_path: Path):
        setup_py._install_foundry_payload(tmp_path)
        with tarfile.open(tmp_path / ".foundry" / "foundry.tar.gz", "r:gz") as tf:
            names = tf.getnames()
        # Tarball uses a top-level wrapper directory
        assert any(n.endswith("/tools/setup.py") for n in names)
        assert any("/skills/" in n for n in names)
        assert any(n.endswith("/mcp-configs/mcp-servers.json") for n in names)

    def test_tarball_excludes_build_artifacts(self, tmp_path: Path):
        setup_py._install_foundry_payload(tmp_path)
        with tarfile.open(tmp_path / ".foundry" / "foundry.tar.gz", "r:gz") as tf:
            names = tf.getnames()
        for forbidden in (".git/", "__pycache__/", ".venv/", "/.claude/", "node_modules/"):
            assert not any(forbidden in n for n in names), (
                f"tarball contains {forbidden}"
            )

    def test_adds_gitignore_entry(self, tmp_path: Path):
        setup_py._install_foundry_payload(tmp_path)
        gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert ".foundry/" in gitignore

    def test_gitignore_entry_not_duplicated(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text(".foundry/\n", encoding="utf-8")
        setup_py._install_foundry_payload(tmp_path)
        content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert content.count(".foundry/") == 1

    def test_gitignore_header_not_duplicated_across_entries(self, tmp_path: Path):
        """The `# claude-foundry payload` comment appears only once even when
        multiple entries (.foundry/, .delegate/, …) are added."""
        setup_py._install_foundry_payload(
            tmp_path, selected_features=["minimax-delegate"]
        )
        content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert content.count("# claude-foundry payload") == 1

    def test_idempotent(self, tmp_path: Path):
        """Running twice yields the same payload structure."""
        setup_py._install_foundry_payload(tmp_path)
        first_paths = sorted(
            p.relative_to(tmp_path).as_posix()
            for p in (tmp_path / ".foundry").rglob("*")
            if p.is_file()
        )
        setup_py._install_foundry_payload(tmp_path)
        second_paths = sorted(
            p.relative_to(tmp_path).as_posix()
            for p in (tmp_path / ".foundry").rglob("*")
            if p.is_file()
        )
        assert first_paths == second_paths

    def test_no_leftover_tmp_tarball(self, tmp_path: Path):
        """The intermediate .tmp file used for atomic-rename must not survive."""
        setup_py._install_foundry_payload(tmp_path)
        assert not (tmp_path / ".foundry" / "foundry.tar.gz.tmp").exists()

    def test_migrates_legacy_claude_foundry(self, tmp_path: Path):
        """A pre-existing <project>/.claude/foundry/ tree must be removed."""
        legacy = tmp_path / ".claude" / "foundry"
        legacy.mkdir(parents=True)
        (legacy / "marker.txt").write_text("legacy junk")
        (legacy / "skills").mkdir()

        setup_py._install_foundry_payload(tmp_path)

        assert not legacy.exists(), "legacy .claude/foundry/ must be removed on install"
        assert (tmp_path / ".foundry" / "foundry.tar.gz").is_file()

    def test_migrates_legacy_staging_dirs(self, tmp_path: Path):
        """Old .claude/.foundry.{new,old} staging dirs must be cleaned up."""
        for stale in (".foundry.new", ".foundry.old"):
            d = tmp_path / ".claude" / stale
            d.mkdir(parents=True)
            (d / "leftover.txt").write_text("from a crashed update")

        setup_py._install_foundry_payload(tmp_path)

        assert not (tmp_path / ".claude" / ".foundry.new").exists()
        assert not (tmp_path / ".claude" / ".foundry.old").exists()

    def test_no_tools_subdir_in_foundry(self, tmp_path: Path):
        """`.foundry/` must contain only the install machinery (setup.py +
        tarball). User-invokable scripts belong inside .claude/."""
        setup_py._install_foundry_payload(
            tmp_path, selected_features=["minimax-delegate"]
        )
        assert not (tmp_path / ".foundry" / "tools").exists(), (
            ".foundry/ must not contain tools/ — scripts ship via the skill"
        )

    def test_delegate_gitignore_entry_when_feature_enabled(self, tmp_path: Path):
        """`.delegate/` must be added to .gitignore when minimax-delegate is on."""
        setup_py._install_foundry_payload(
            tmp_path, selected_features=["minimax-delegate"]
        )
        gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert ".delegate/" in gitignore

    def test_delegate_gitignore_absent_when_feature_disabled(self, tmp_path: Path):
        """Don't pollute .gitignore with .delegate/ if the feature isn't on."""
        setup_py._install_foundry_payload(tmp_path, selected_features=[])
        gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert ".delegate/" not in gitignore

    def test_skips_when_repo_root_inside_target(self, tmp_path: Path, monkeypatch):
        """Don't write payload if REPO_ROOT is already inside the project."""
        fake_root = tmp_path / ".foundry-source"
        fake_root.mkdir()
        monkeypatch.setattr(setup_py, "REPO_ROOT", fake_root)

        setup_py._install_foundry_payload(tmp_path)

        # Nothing should have been written under .foundry/
        assert not (tmp_path / ".foundry" / "foundry.tar.gz").exists()
        assert not (tmp_path / ".foundry" / "setup.py").exists()

    def test_migration_from_inside_legacy_location(
        self, tmp_path: Path, monkeypatch
    ):
        """When invoked by the OLD update-foundry.sh, the new setup.py runs
        from inside <project>/.claude/foundry/. That run must:
          1. NOT rmtree the legacy dir mid-run (it's the dir we're in)
          2. Still install the new .foundry/ payload
          3. Schedule legacy cleanup for atexit (deferred until after exit)
        """
        legacy = tmp_path / ".claude" / "foundry"
        legacy.parent.mkdir(parents=True)
        shutil.copytree(REPO_ROOT, legacy, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".venv", "venv", "node_modules",
            "results", ".foundry", ".claude",
        ))

        monkeypatch.setattr(setup_py, "REPO_ROOT", legacy)

        registered: list[tuple] = []
        import atexit as _atexit
        monkeypatch.setattr(
            _atexit,
            "register",
            lambda fn, *args, **kw: registered.append((fn, args, kw)),
        )

        setup_py._install_foundry_payload(tmp_path)

        # (1) Legacy still exists — deletion was deferred
        assert legacy.is_dir(), "legacy dir must NOT be removed mid-run"
        # (2) New payload was installed
        assert (tmp_path / ".foundry" / "foundry.tar.gz").is_file()
        assert (tmp_path / ".foundry" / "setup.py").is_file()
        # (3) atexit cleanup was scheduled for the legacy dir
        assert any(
            args and str(args[0]) == str(legacy) for _, args, _ in registered
        ), f"expected atexit cleanup of {legacy}, got: {registered}"


class TestFeatureRequiredSkills:
    """Verify FEATURE_REQUIRED_SKILLS shape and that minimax-delegate
    requires the delegate skill (so stale manifests self-heal)."""

    def test_constant_exists(self):
        assert hasattr(setup_py, "FEATURE_REQUIRED_SKILLS")
        assert isinstance(setup_py.FEATURE_REQUIRED_SKILLS, dict)

    def test_minimax_delegate_requires_delegate_skill(self):
        """The whole point of this constant: minimax-delegate is non-functional
        without the delegate skill (which carries the run.sh/lib.sh scripts)."""
        required = setup_py.FEATURE_REQUIRED_SKILLS.get("minimax-delegate", [])
        assert "delegate" in required, (
            "minimax-delegate must require the delegate skill — without it, "
            "the deployed feature has no run.sh/lib.sh to invoke"
        )

    def test_required_skills_exist_in_SKILLS(self):
        """Every required skill must exist in the SKILLS catalog."""
        for feature, skills in setup_py.FEATURE_REQUIRED_SKILLS.items():
            for skill in skills:
                assert skill in setup_py.SKILLS, (
                    f"FEATURE_REQUIRED_SKILLS[{feature!r}] references "
                    f"unknown skill {skill!r}"
                )

    def test_no_overlap_between_required_and_suggested(self):
        """A skill should be in REQUIRED or SUGGESTED, not both — the lists
        have different semantics (required = mandatory, suggested = default)."""
        for feature in setup_py.FEATURE_REQUIRED_SKILLS:
            req = set(setup_py.FEATURE_REQUIRED_SKILLS.get(feature, []))
            sug = set(setup_py.FEATURE_SUGGESTED_SKILLS.get(feature, []))
            overlap = req & sug
            assert not overlap, (
                f"feature {feature!r} has skills in both REQUIRED and "
                f"SUGGESTED: {overlap}. Pick one — REQUIRED implies mandatory, "
                f"SUGGESTED implies default-but-removable."
            )


class TestUpdateFoundryScript:
    """Verify update-foundry.sh targets the new <project>/.foundry/ payload layout."""

    SCRIPT = REPO_ROOT / "skills" / "update-foundry" / "scripts" / "update-foundry.sh"

    def test_script_exists_and_parses(self):
        assert self.SCRIPT.is_file()
        import subprocess
        result = subprocess.run(
            ["bash", "-n", str(self.SCRIPT)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"bash syntax error:\n{result.stderr}"

    def test_script_targets_dot_foundry_dir(self):
        """Should write under <project>/.foundry/, not the legacy .claude/foundry/."""
        content = self.SCRIPT.read_text(encoding="utf-8")
        assert "PROJECT_DIR/.foundry" in content
        # The legacy path must not appear as a write target anymore
        assert ".claude/foundry" not in content

    def test_script_writes_tarball_and_setup_py(self):
        content = self.SCRIPT.read_text(encoding="utf-8")
        assert "foundry.tar.gz" in content
        assert "tools/setup.py" in content

    def test_script_does_atomic_tarball_swap(self):
        content = self.SCRIPT.read_text(encoding="utf-8")
        # Stage as .new, back up as .old, mv into place
        assert "foundry.tar.gz.new" in content
        assert "foundry.tar.gz.old" in content

    def test_script_rolls_back_on_setup_failure(self):
        content = self.SCRIPT.read_text(encoding="utf-8")
        assert "rolling back" in content.lower() or "roll back" in content.lower()

    def test_script_invokes_deployed_setup_py(self):
        """Must run <project>/.foundry/setup.py, not python -m or anything else."""
        content = self.SCRIPT.read_text(encoding="utf-8")
        assert '"$SETUP_PY" init' in content

    def test_script_prints_manual_reinit_hint(self):
        content = self.SCRIPT.read_text(encoding="utf-8")
        assert "Manual re-init" in content or "manual re-init" in content.lower()

    def test_no_grep_q_under_pipefail_for_setup_py_check(self):
        """Regression guard: the tarball sanity check must NOT use `grep -q`
        in a pipeline under `set -o pipefail`. grep -q exits on first match
        and closes its stdin, causing tar to receive SIGPIPE and exit
        non-zero — pipefail then propagates that as a pipeline failure,
        making the check report a false negative. Use grep -c into a
        variable (which reads all input) instead."""
        content = self.SCRIPT.read_text(encoding="utf-8")
        # Confirm the script enables pipefail (the bug only triggers there)
        assert "set -euo pipefail" in content or "set -o pipefail" in content
        # Find the setup-py sanity check region and ensure it doesn't
        # use grep -q on a tar | grep pipeline.
        bad_pattern = "tar $TAR_FLAGS -tzf"
        for i, line in enumerate(content.splitlines()):
            if bad_pattern in line and "grep -q" in line:
                raise AssertionError(
                    f"line {i + 1}: pipeline `tar | grep -q` under pipefail "
                    f"causes SIGPIPE-induced false negatives. Use `grep -c` "
                    f"with the result captured in a variable instead.\n"
                    f"Offending line: {line.strip()}"
                )

    def test_setup_py_check_uses_grep_c(self):
        """Positive form of the regression guard above: confirm we capture
        a count from grep -c rather than relying on grep -q's exit code."""
        content = self.SCRIPT.read_text(encoding="utf-8")
        assert "grep -c '/tools/setup.py$'" in content, (
            "expected grep -c (counts all matches, reads entire stdin) "
            "for the tarball sanity check"
        )
