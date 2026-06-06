"""Regression tests for issues #25 (stale rule files) and #26 (Windows Unicode crash).

Issue #25 — copy_rules() used to deploy new files but never remove files
that fell out of the selection. A template migration (e.g. gui.md +
python-qt.md + gui-threading.md → desktop-gui-qt.md) would leave the old
rule files lingering in .claude/rules/, causing Claude to load duplicate
or conflicting instructions. Fix: cleanup pass that removes any .md file
not in the current deployment, preserving private-prefixed files.

Issue #26 — setup.py prints Unicode characters (✓, ✗, ⚠, em dashes, etc.)
which crash with UnicodeEncodeError on Windows cp1252 consoles. Fix:
_ensure_utf8_stdio() runs at module import time and reconfigures stdout/
stderr to UTF-8 with errors='replace'. These tests verify that the
reconfigure is safe on various stream types and actually prevents the
crash when stdio is cp1252.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import setup as setup_py  # noqa: E402

# ── Issue #25: stale rule cleanup ─────────────────────────────────────


class TestStaleRuleCleanup:
    """copy_rules() must remove rule files that fell out of the selection."""

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        """A fresh tmp project with .claude/rules/ pre-populated as if from
        a previous setup.py init run that used the old template structure."""
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        # Simulate stale files from the old GUI template structure
        # (the exact scenario from the issue body: kalimbascope_test on Windows)
        (rules_dir / "gui.md").write_text("# Old GUI rules (stale)\n", encoding="utf-8")
        (rules_dir / "python-qt.md").write_text("# Old Python-Qt (stale)\n", encoding="utf-8")
        (rules_dir / "gui-threading.md").write_text("# Old threading (stale)\n", encoding="utf-8")
        return tmp_path

    def test_deploys_new_selection(self, project: Path):
        """Baseline: after copy_rules, the selected rules are on disk."""
        setup_py.copy_rules(
            project,
            base=["security.md", "coding-style.md"],
            modular={},
        )
        rules_dir = project / ".claude" / "rules"
        assert (rules_dir / "security.md").is_file()
        assert (rules_dir / "coding-style.md").is_file()

    def test_removes_stale_rules_not_in_new_selection(self, project: Path):
        """The exact migration scenario from the issue: replacing the old
        gui.md + python-qt.md + gui-threading.md trio with desktop-gui-qt.md
        must strip all three stale files."""
        setup_py.copy_rules(
            project,
            base=["security.md"],
            modular={"templates": ["desktop-gui-qt.md"]},
        )
        rules_dir = project / ".claude" / "rules"
        # New selection is deployed
        assert (rules_dir / "security.md").is_file()
        assert (rules_dir / "desktop-gui-qt.md").is_file()
        # Stale files are gone
        assert not (rules_dir / "gui.md").exists()
        assert not (rules_dir / "python-qt.md").exists()
        assert not (rules_dir / "gui-threading.md").exists()

    def test_preserves_private_prefixed_rules(self, project: Path):
        """Private source files (e.g. company-*.md) must survive cleanup."""
        rules_dir = project / ".claude" / "rules"
        (rules_dir / "company-style.md").write_text("# Company style\n", encoding="utf-8")
        (rules_dir / "company-security.md").write_text("# Company sec\n", encoding="utf-8")
        (rules_dir / "acme-corp-foo.md").write_text("# Acme rule\n", encoding="utf-8")

        setup_py.copy_rules(
            project,
            base=["security.md"],
            modular={},
            private_prefixes=["company", "acme-corp"],
        )
        # Stale base rules are cleaned up
        assert not (rules_dir / "gui.md").exists()
        # Private-prefixed files survive
        assert (rules_dir / "company-style.md").is_file()
        assert (rules_dir / "company-security.md").is_file()
        assert (rules_dir / "acme-corp-foo.md").is_file()

    def test_idempotent(self, project: Path):
        """Running copy_rules twice with the same selection is a no-op the
        second time (no rule files are added, removed, or modified)."""
        setup_py.copy_rules(
            project,
            base=["security.md"],
            modular={"lang": ["python.md"]},
        )
        rules_dir = project / ".claude" / "rules"
        first = {f.name: f.stat().st_mtime_ns for f in rules_dir.iterdir() if f.is_file()}

        setup_py.copy_rules(
            project,
            base=["security.md"],
            modular={"lang": ["python.md"]},
        )
        second = {f.name: f.stat().st_mtime_ns for f in rules_dir.iterdir() if f.is_file()}
        assert set(first.keys()) == set(second.keys()), (
            "File set changed between two identical copy_rules calls"
        )

    def test_cleanup_does_not_touch_subdirectories(self, tmp_path: Path):
        """If a user has subdirectories under .claude/rules/ for any reason,
        the cleanup must not recurse into them."""
        rules_dir = tmp_path / ".claude" / "rules"
        (rules_dir / "nested").mkdir(parents=True)
        (rules_dir / "nested" / "sub.md").write_text("# nested\n", encoding="utf-8")
        (rules_dir / "stale.md").write_text("# stale\n", encoding="utf-8")

        setup_py.copy_rules(
            tmp_path,
            base=["security.md"],
            modular={},
        )
        assert not (rules_dir / "stale.md").exists(), "flat .md file should be removed"
        assert (rules_dir / "nested" / "sub.md").is_file(), (
            "subdirectory contents must be preserved — cleanup is not recursive"
        )

    def test_cleanup_does_not_touch_non_md_files(self, project: Path):
        """Non-.md files in the rules dir are out of scope for rule cleanup."""
        rules_dir = project / ".claude" / "rules"
        (rules_dir / "notes.txt").write_text("user notes", encoding="utf-8")
        (rules_dir / "README").write_text("rules readme", encoding="utf-8")

        setup_py.copy_rules(
            project,
            base=["security.md"],
            modular={},
        )
        assert (rules_dir / "notes.txt").is_file(), "non-.md file should not be removed"
        assert (rules_dir / "README").is_file(), "extensionless file should not be removed"

    def test_empty_selection_clears_foundry_rules(self, project: Path):
        """Calling copy_rules with no base and no modular removes all
        foundry-managed rules (but private-prefixed ones survive)."""
        rules_dir = project / ".claude" / "rules"
        (rules_dir / "company-x.md").write_text("company", encoding="utf-8")

        setup_py.copy_rules(
            project,
            base=[],
            modular={},
            private_prefixes=["company"],
        )
        assert not (rules_dir / "gui.md").exists()
        assert not (rules_dir / "python-qt.md").exists()
        assert not (rules_dir / "gui-threading.md").exists()
        assert (rules_dir / "company-x.md").is_file()


# ── Issue #26: Windows Unicode crash ──────────────────────────────────


class TestUtf8StdioReconfigure:
    """_ensure_utf8_stdio() must prevent Unicode print crashes on cp1252."""

    # Characters that crashed on the original issue's Windows cp1252 console.
    # Keep this list aligned with the issue body.
    CRASHING_CHARS = ["✓", "✗", "⚠", "—"]

    def test_ensure_utf8_stdio_is_callable_and_safe(self):
        """Calling it on the real stdout/stderr must not raise."""
        setup_py._ensure_utf8_stdio()  # just verify no exception

    def test_noop_when_stdout_already_utf8(self, monkeypatch):
        """When stdout is already UTF-8, reconfigure() should not be called —
        or if it IS called, it must not change anything observable."""
        # Simulate a utf-8 TextIOWrapper; reconfigure should be a no-op.
        buf = io.BytesIO()
        wrapper = io.TextIOWrapper(buf, encoding="utf-8")
        monkeypatch.setattr(sys, "stdout", wrapper)
        setup_py._ensure_utf8_stdio()
        assert wrapper.encoding.lower() == "utf-8"
        # Still writable with Unicode
        wrapper.write("✓\n")
        wrapper.flush()

    def test_reconfigures_cp1252_stdout_to_utf8(self, monkeypatch):
        """The critical regression test: a cp1252 TextIOWrapper must be
        upgraded to UTF-8 so subsequent prints of ✓/✗/⚠ don't raise."""
        buf = io.BytesIO()
        wrapper = io.TextIOWrapper(buf, encoding="cp1252", newline="")
        monkeypatch.setattr(sys, "stdout", wrapper)

        setup_py._ensure_utf8_stdio()

        assert sys.stdout.encoding.lower() == "utf-8", (
            "_ensure_utf8_stdio must reconfigure cp1252 stdout to utf-8"
        )

    def test_cp1252_stdout_can_print_unicode_after_reconfigure(self, monkeypatch, capsys):
        """End-to-end: simulate cp1252 stdout, reconfigure, print all the
        issue's problem characters, verify no crash."""
        buf = io.BytesIO()
        wrapper = io.TextIOWrapper(buf, encoding="cp1252", newline="")
        monkeypatch.setattr(sys, "stdout", wrapper)
        setup_py._ensure_utf8_stdio()
        # Should not raise
        for char in self.CRASHING_CHARS:
            print(char, file=sys.stdout)
        sys.stdout.flush()
        # Verify the bytes were actually written (as utf-8)
        output = buf.getvalue()
        for char in self.CRASHING_CHARS:
            assert char.encode("utf-8") in output, (
                f"{char!r} was not encoded as UTF-8 in output"
            )

    def test_cp1252_without_reconfigure_would_crash(self, monkeypatch):
        """Control test: verify the baseline failure mode — cp1252 stdout
        without the reconfigure DOES raise UnicodeEncodeError. This
        confirms our test harness accurately reproduces the bug."""
        buf = io.BytesIO()
        wrapper = io.TextIOWrapper(buf, encoding="cp1252", newline="")
        monkeypatch.setattr(sys, "stdout", wrapper)
        # Deliberately do NOT call _ensure_utf8_stdio
        with pytest.raises(UnicodeEncodeError):
            sys.stdout.write("✓")
            sys.stdout.flush()

    def test_safe_with_stream_missing_reconfigure(self, monkeypatch):
        """If sys.stdout has been replaced with something that has no
        reconfigure method (e.g. a test harness using StringIO), the
        function must not raise — it should skip silently."""
        class FakeStream:
            encoding = "cp1252"
            # Note: no reconfigure() method
            def write(self, s): pass
            def flush(self): pass

        monkeypatch.setattr(sys, "stdout", FakeStream())
        # Must not raise
        setup_py._ensure_utf8_stdio()

    def test_safe_with_stream_no_encoding(self, monkeypatch):
        """Streams with encoding=None (rare but possible) must not crash."""
        class FakeStream:
            encoding = None
            def write(self, s): pass
            def flush(self): pass

        monkeypatch.setattr(sys, "stdout", FakeStream())
        setup_py._ensure_utf8_stdio()  # no raise

    def test_errors_replace_handles_unmappable_chars(self, monkeypatch):
        """With errors='replace', any character that can't be encoded
        should become a replacement character instead of raising. Since
        we reconfigure to utf-8 which handles everything, this is more
        of a belt-and-suspenders check — mostly verifying the flag is set."""
        buf = io.BytesIO()
        wrapper = io.TextIOWrapper(buf, encoding="cp1252", newline="")
        monkeypatch.setattr(sys, "stdout", wrapper)
        setup_py._ensure_utf8_stdio()
        # The errors attribute on the reconfigured wrapper should be 'replace'
        assert sys.stdout.errors == "replace"
