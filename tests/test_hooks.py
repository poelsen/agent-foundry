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


def _run_hook(script: str, file_path: Path, stub_dir: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(file_path)}})
    env = {**os.environ, "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(["bash", str(HOOK_LIB / script)], input=payload, text=True,
                          capture_output=True, env=env, cwd=file_path.parent, timeout=30)


@pytest.mark.skipif(shutil.which("jq") is None, reason="hook scripts need jq")
@pytest.mark.parametrize("script", sorted(CASES))
def test_hook_filters_by_extension(script: str, tmp_path: Path):
    tool, match, ignore = CASES[script]
    log = tmp_path / "calls.log"
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / tool
    stub.write_text(f'#!/bin/bash\necho "$@" >> "{log}"\n')
    stub.chmod(0o755)
    # tsc-check only runs inside a TypeScript project
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text("{}")
    for name in (match, ignore):
        (tmp_path / name).write_text("")

    ignored = _run_hook(script, tmp_path / ignore, stub_dir)
    assert ignored.returncode == 0
    assert not log.exists(), f"{script} ran {tool} on {ignore}"
    assert json.loads(ignored.stdout)["tool_input"]["file_path"].endswith(ignore)

    matched = _run_hook(script, tmp_path / match, stub_dir)
    assert matched.returncode == 0
    assert log.exists(), f"{script} did not run {tool} on {match}"
