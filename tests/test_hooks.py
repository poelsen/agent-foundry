"""Tests for Claude Code hook wiring: settings.json matchers and the scripts' own file filters."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import pytest

from foundry.deploy import EDIT_TOOLS_MATCHER, generate_settings_json
from foundry.registry import HOOK_SCRIPTS

HOOK_LIB = Path(__file__).parent.parent / "cli" / "claude" / "hooks" / "library"

# script → (tool it runs, a file it must act on, a file it must ignore)
CASES = {
    "ruff-format.sh": ("ruff", "mod.py", "README.md"),
    "mypy-check.sh": ("mypy", "mod.py", "mod.rs"),
    "prettier-format.sh": ("prettier", "app.jsx", "mod.py"),
    "tsc-check.sh": ("npx", "app.ts", "app.js"),
    "cargo-check.sh": ("cargo", "lib.rs", "Cargo.toml"),
}


def test_every_hook_uses_tool_name_matcher():
    settings = generate_settings_json(list(HOOK_SCRIPTS), [])
    entries = settings["hooks"]["PostToolUse"]
    assert len(entries) == len(HOOK_SCRIPTS)
    assert {e["matcher"] for e in entries} == {EDIT_TOOLS_MATCHER}
    # A plain tool-name regex, not the old never-matching expression syntax
    assert "==" not in EDIT_TOOLS_MATCHER and "tool_input" not in EDIT_TOOLS_MATCHER


def test_cases_cover_every_shipped_hook():
    assert set(CASES) == set(HOOK_SCRIPTS)


def _stub_tool(tmp_path: Path, tool: str) -> tuple[Path, Path]:
    """A fake `tool` on PATH that logs its arguments. Returns (bin dir, log)."""
    log = tmp_path / "calls.log"
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / tool
    stub.write_text(f'#!/bin/bash\necho "$@" >> "{log}"\n')
    stub.chmod(0o755)
    return stub_dir, log


def _run_hook(script: str, payload: dict, cwd: Path, stub_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(["bash", str(HOOK_LIB / script)], input=json.dumps(payload), text=True,
                          capture_output=True, env=env, cwd=cwd, timeout=30)


def _claude_payload(path: Path) -> dict:
    return {"tool_name": "Edit", "cwd": str(path.parent),
            "tool_input": {"file_path": str(path)}}


def _codex_payload(cwd: Path, patch_lines: list[str]) -> dict:
    patch = "\n".join(["*** Begin Patch", *patch_lines, "*** End Patch", ""])
    return {"tool_name": "apply_patch", "cwd": str(cwd), "tool_input": {"command": patch}}


needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="hook scripts need jq")


@needs_jq
@pytest.mark.parametrize("script", sorted(CASES))
def test_hook_filters_by_extension(script: str, tmp_path: Path):
    tool, match, ignore = CASES[script]
    stub_dir, log = _stub_tool(tmp_path, tool)
    # tsc-check only runs inside a TypeScript project
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text("{}")
    for name in (match, ignore):
        (tmp_path / name).write_text("")

    ignored = _run_hook(script, _claude_payload(tmp_path / ignore), tmp_path, stub_dir)
    assert ignored.returncode == 0
    assert not log.exists(), f"{script} ran {tool} on {ignore}"
    # Nothing on stdout: Codex fails any hook whose stdout is non-hook JSON
    assert ignored.stdout == ""

    matched = _run_hook(script, _claude_payload(tmp_path / match), tmp_path, stub_dir)
    assert matched.returncode == 0
    assert log.exists(), f"{script} did not run {tool} on {match}"
    assert matched.stdout == ""


@needs_jq
def test_codex_patch_files_resolved_from_cwd(tmp_path: Path):
    stub_dir, log = _stub_tool(tmp_path, "ruff")
    (tmp_path / "src").mkdir()
    for name in ("src/new.py", "edited.py", "moved.py", "notes.md"):
        (tmp_path / name).write_text("")
    payload = _codex_payload(tmp_path, [
        "*** Add File: src/new.py", "+x = 1",
        "*** Update File: edited.py", "@@", "-a", "+b",
        "*** Update File: old.py", "*** Move to: moved.py",
        "*** Update File: notes.md",
        "*** Delete File: gone.py",
    ])
    result = _run_hook("ruff-format.sh", payload, tmp_path / "src", stub_dir)  # cwd from payload
    assert result.returncode == 0 and result.stdout == ""
    calls = log.read_text().splitlines()
    assert calls == ["format src/new.py", "format edited.py", "format moved.py"]


@needs_jq
def test_antigravity_payload_uses_target_file_and_workspace(tmp_path: Path):
    stub_dir, log = _stub_tool(tmp_path, "mypy")
    (tmp_path / "mod.py").write_text("")
    (tmp_path / ".agents").mkdir()
    payload = {"workspacePaths": [str(tmp_path)],
               "toolCall": {"name": "write_to_file",
                            "args": {"TargetFile": str(tmp_path / "mod.py")}}}
    # agy runs hooks from .agents/; mypy must run from the workspace root
    stub = stub_dir / "mypy"
    stub.write_text(f'#!/bin/bash\necho "$(pwd) $@" >> "{log}"\n')
    result = _run_hook("mypy-check.sh", payload, tmp_path / ".agents", stub_dir)
    assert result.returncode == 0 and result.stdout == ""
    assert log.read_text().split()[0] == str(tmp_path)
    assert str(tmp_path / "mod.py") in log.read_text()


@needs_jq
def test_cargo_check_runs_once_per_patch(tmp_path: Path):
    stub_dir, log = _stub_tool(tmp_path, "cargo")
    for name in ("a.rs", "b.rs"):
        (tmp_path / name).write_text("")
    payload = _codex_payload(tmp_path, ["*** Update File: a.rs", "*** Update File: b.rs"])
    _run_hook("cargo-check.sh", payload, tmp_path, stub_dir)
    assert len(log.read_text().splitlines()) == 1


@needs_jq
def test_tsc_check_reports_errors_for_edited_file(tmp_path: Path):
    """tsc prints project-relative paths; the hook must match them."""
    stub_dir, _ = _stub_tool(tmp_path, "unused")
    npx = stub_dir / "npx"
    npx.write_text("#!/bin/bash\necho 'src/app.ts(1,1): error TS1005: oops'\n"
                   "echo 'src/other.ts(2,2): error TS1005: unrelated'\n")
    npx.chmod(0o755)
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text("{}")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("")
    result = _run_hook("tsc-check.sh", _claude_payload(tmp_path / "src" / "app.ts"),
                       tmp_path, stub_dir)
    assert "src/app.ts(1,1)" in result.stderr
    assert "other.ts" not in result.stderr
