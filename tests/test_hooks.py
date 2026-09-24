"""Tests for the foundry hook scripts and their wiring into each CLI.

The scripts run for real under bash; the tools they drive (ruff, mypy,
prettier, npx, cargo) are stubs on PATH that log their arguments.
"""

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

# script → (tool it runs, a file it acts on, a file it ignores, project config enabling it)
CASES = {
    "ruff-format.sh": ("ruff", "mod.py", "README.md", {"pyproject.toml": "[tool.ruff.format]\n"}),
    "mypy-check.sh": ("mypy", "mod.py", "mod.rs", {"mypy.ini": "[mypy]\n"}),
    "prettier-format.sh": ("prettier", "app.jsx", "mod.py", {".prettierrc": "{}"}),
    "tsc-check.sh": ("npx", "app.ts", "app.js", {"package.json": "{}", "tsconfig.json": "{}"}),
    "cargo-check.sh": ("cargo", "lib.rs", "Cargo.toml", {"Cargo.toml": "[package]\n"}),
}

needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="hook scripts need jq")


def test_every_hook_uses_tool_name_matcher():
    settings = generate_settings_json(list(HOOK_SCRIPTS), [])
    entries = settings["hooks"]["PostToolUse"]
    assert len(entries) == len(HOOK_SCRIPTS)
    assert {e["matcher"] for e in entries} == {EDIT_TOOLS_MATCHER}
    # A plain tool-name regex, not the old never-matching expression syntax
    assert "==" not in EDIT_TOOLS_MATCHER and "tool_input" not in EDIT_TOOLS_MATCHER
    # Anchored to the project, so hooks work from a subdirectory too
    assert all(e["hooks"][0]["command"].startswith('"$CLAUDE_PROJECT_DIR"/.claude/hooks/')
               for e in entries)


def test_cases_cover_every_shipped_hook():
    assert set(CASES) == set(HOOK_SCRIPTS)


def _stub_tool(tmp_path: Path, tool: str, output: str = "") -> tuple[Path, Path]:
    """A fake `tool` on PATH that logs its arguments (and prints ``output``)."""
    log = tmp_path / "calls.log"
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    stub = stub_dir / tool
    stub.write_text(f'#!/bin/bash\necho "$@" >> "{log}"\nprintf "%s\\n" "{output}"\n')
    stub.chmod(0o755)
    return stub_dir, log


def _run_hook(script: str, payload: dict, cwd: Path, stub_dir: Path,
              path: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": path or f"{stub_dir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(["bash", str(HOOK_LIB / script)], input=json.dumps(payload), text=True,
                          capture_output=True, env=env, cwd=cwd, timeout=30)


def _claude_payload(path: Path) -> dict:
    return {"tool_name": "Edit", "cwd": str(path.parent),
            "tool_input": {"file_path": str(path)}}


def _codex_payload(cwd: Path, patch_lines: list[str]) -> dict:
    patch = "\n".join(["*** Begin Patch", *patch_lines, "*** End Patch", ""])
    return {"tool_name": "apply_patch", "cwd": str(cwd), "tool_input": {"command": patch}}


def _agy_payload(workspace: Path, target: Path) -> dict:
    return {"workspacePaths": [str(workspace)],
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": str(target)}}}


def _project(tmp_path: Path, script: str, configured: bool = True) -> Path:
    _, match, ignore, config = CASES[script]
    if configured:
        for name, content in config.items():
            (tmp_path / name).write_text(content)
    for name in (match, ignore):
        if not (tmp_path / name).exists():
            (tmp_path / name).write_text("")
    return tmp_path


@needs_jq
@pytest.mark.parametrize("script", sorted(CASES))
def test_hook_filters_by_extension(script: str, tmp_path: Path):
    tool, match, ignore, _ = CASES[script]
    stub_dir, log = _stub_tool(tmp_path, tool)
    _project(tmp_path, script)

    ignored = _run_hook(script, _claude_payload(tmp_path / ignore), tmp_path, stub_dir)
    assert ignored.returncode == 0
    assert not log.exists(), f"{script} ran {tool} on {ignore}"
    assert ignored.stdout == ""  # Codex fails any hook whose stdout is non-hook JSON

    matched = _run_hook(script, _claude_payload(tmp_path / match), tmp_path, stub_dir)
    assert matched.returncode == 0
    assert log.exists(), f"{script} did not run {tool} on {match}"
    assert matched.stdout == ""  # no errors to report


@needs_jq
@pytest.mark.parametrize("script", ["ruff-format.sh", "prettier-format.sh", "mypy-check.sh"])
def test_hook_skips_projects_without_tool_config(script: str, tmp_path: Path):
    """A black-formatted (or unformatted) project must not get ruff rewrites."""
    tool, match, _, _ = CASES[script]
    stub_dir, log = _stub_tool(tmp_path, tool)
    _project(tmp_path, script, configured=False)
    (tmp_path / "pyproject.toml").write_text("[tool.black]\nline-length = 110\n")
    result = _run_hook(script, _claude_payload(tmp_path / match), tmp_path, stub_dir)
    assert result.returncode == 0 and not log.exists()


@needs_jq
@pytest.mark.parametrize("files, formats", [
    ({"pyproject.toml": "[tool.ruff.lint]\nselect = ['E']\n"}, False),          # lint-only
    ({"ruff.toml": "[lint]\nselect = ['E']\n"}, False),                          # lint-only
    ({"pyproject.toml": "[tool.black]\n[tool.ruff.format]\n"}, False),           # black wins
    ({"ruff.toml": "[format]\n", ".pre-commit-config.yaml": "- id: black\n"}, False),
    ({".pre-commit-config.yaml": "# no ruff-format here\n- id: black\n"}, False),
    ({"ruff.toml": "[format]\nquote-style = 'single'\n"}, True),
    ({".ruff.toml": "format.quote-style = 'single'\n"}, True),
    ({".pre-commit-config.yaml": "  - id: ruff-format\n"}, True),
])
def test_ruff_needs_a_format_signal_and_no_black(tmp_path: Path, files: dict, formats: bool):
    stub_dir, log = _stub_tool(tmp_path, "ruff")
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    (tmp_path / "mod.py").write_text("")
    _run_hook("ruff-format.sh", _claude_payload(tmp_path / "mod.py"), tmp_path, stub_dir)
    assert log.exists() is formats


@needs_jq
def test_config_at_the_repository_root_still_counts(tmp_path: Path):
    stub_dir, log = _stub_tool(tmp_path, "ruff")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "ruff.toml").write_text("[format]\n")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "mod.py").write_text("")
    _run_hook("ruff-format.sh", _claude_payload(repo / "pkg" / "mod.py"), repo, stub_dir)
    assert log.exists()


@needs_jq
def test_config_above_the_repository_root_is_ignored(tmp_path: Path):
    stub_dir, log = _stub_tool(tmp_path, "ruff")
    (tmp_path / "ruff.toml").write_text("[format]\n")  # e.g. a stray ~/ruff.toml
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "mod.py").write_text("")
    _run_hook("ruff-format.sh", _claude_payload(repo / "mod.py"), repo, stub_dir)
    assert not log.exists()


@needs_jq
def test_large_reports_are_capped_and_labelled(tmp_path: Path):
    stub_dir, _ = _stub_tool(tmp_path, "mypy", output="x.py:1: error: " + "e" * 400)
    (tmp_path / "mypy.ini").write_text("[mypy]\n")
    names = [f"m{i}.py" for i in range(80)]
    for name in names:
        (tmp_path / name).write_text("")
    payload = _codex_payload(tmp_path, [f"*** Update File: {n}" for n in names])
    result = _run_hook("mypy-check.sh", payload, tmp_path, stub_dir)
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert context.startswith("[agent-foundry mypy hook — tool diagnostics")
    assert "truncated after 8000 characters" in context and len(context) < 8400


@needs_jq
def test_tool_config_found_in_parent_directory(tmp_path: Path):
    stub_dir, log = _stub_tool(tmp_path, "ruff")
    (tmp_path / "ruff.toml").write_text("[format]\n")
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    target = tmp_path / "pkg" / "sub" / "mod.py"
    target.write_text("")
    _run_hook("ruff-format.sh", _claude_payload(target), tmp_path, stub_dir)
    assert log.exists()


@needs_jq
def test_check_errors_reach_the_agent_as_context(tmp_path: Path):
    stub_dir, _ = _stub_tool(tmp_path, "mypy", output="mod.py:1: error: Name 'x' is not defined")
    _project(tmp_path, "mypy-check.sh")
    result = _run_hook("mypy-check.sh", _claude_payload(tmp_path / "mod.py"), tmp_path, stub_dir)
    out = json.loads(result.stdout)  # exactly one hook-output object
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "Name 'x' is not defined" in out["hookSpecificOutput"]["additionalContext"]
    assert result.returncode == 0  # context, never a block


@needs_jq
def test_codex_patch_files_resolved_from_cwd(tmp_path: Path):
    stub_dir, log = _stub_tool(tmp_path, "ruff")
    (tmp_path / "ruff.toml").write_text("[format]\n")
    (tmp_path / "src").mkdir()
    for name in ("src/new.py", "edited.py", "moved.py", "notes.md", "-dash.py"):
        (tmp_path / name).write_text("")
    payload = _codex_payload(tmp_path, [
        "*** Add File: src/new.py", "+x = 1",
        "*** Update File: edited.py", "@@", "-a", "+b",
        "*** Update File: old.py", "*** Move to: moved.py",
        "*** Update File: notes.md",
        "*** Update File: -dash.py",
        "*** Delete File: gone.py",
    ])
    result = _run_hook("ruff-format.sh", payload, tmp_path / "src", stub_dir)  # cwd from payload
    assert result.returncode == 0 and result.stdout == ""
    calls = log.read_text().splitlines()
    # "-dash.py" is passed as "./-dash.py" so ruff can't read it as an option
    assert calls == ["format src/new.py", "format edited.py", "format moved.py",
                     "format ./-dash.py"]


@needs_jq
def test_antigravity_gets_json_object_and_workspace_cwd(tmp_path: Path):
    stub_dir, log = _stub_tool(tmp_path, "mypy")
    (stub_dir / "mypy").write_text(f'#!/bin/bash\necho "$(pwd) $@" >> "{log}"\n'
                                   'echo "mod.py:1: error: boom"\n')
    (tmp_path / "mypy.ini").write_text("[mypy]\n")
    (tmp_path / "mod.py").write_text("")
    (tmp_path / ".agents").mkdir()
    # agy runs hooks from .agents/; mypy must run from the workspace root
    result = _run_hook("mypy-check.sh", _agy_payload(tmp_path, tmp_path / "mod.py"),
                       tmp_path / ".agents", stub_dir)
    assert result.returncode == 0
    assert result.stdout == "{}\n"          # Antigravity's required PostToolUse answer
    assert "error: boom" in result.stderr    # no context channel there; diagnostics to stderr
    assert log.read_text().split()[0] == str(tmp_path)


@needs_jq
def test_cargo_check_runs_once_per_patch(tmp_path: Path):
    stub_dir, log = _stub_tool(tmp_path, "cargo")
    (tmp_path / "Cargo.toml").write_text("[package]\n")
    for name in ("a.rs", "b.rs"):
        (tmp_path / name).write_text("")
    payload = _codex_payload(tmp_path, ["*** Update File: a.rs", "*** Update File: b.rs"])
    _run_hook("cargo-check.sh", payload, tmp_path, stub_dir)
    calls = log.read_text().splitlines()
    assert len(calls) == 1 and f"--manifest-path {tmp_path}/Cargo.toml" in calls[0]


@needs_jq
def test_tsc_check_uses_local_compiler_and_reports_edited_file(tmp_path: Path):
    """tsc prints project-relative paths; the hook must match them, and never
    let npx download a package."""
    stub_dir, log = _stub_tool(tmp_path, "npx")
    (stub_dir / "npx").write_text(f'#!/bin/bash\necho "$@" >> "{log}"\n'
                                  "echo 'src/app.ts(1,1): error TS1005: oops'\n"
                                  "echo 'src/other.ts(2,2): error TS1005: unrelated'\n")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text("{}")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("")
    result = _run_hook("tsc-check.sh", _claude_payload(tmp_path / "src" / "app.ts"),
                       tmp_path, stub_dir)
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "src/app.ts(1,1)" in context and "other.ts" not in context
    assert log.read_text().startswith("--no-install tsc")


@needs_jq
def test_missing_jq_is_reported_not_silent(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("bash", "cat", "dirname", "printf"):
        (bin_dir / tool).symlink_to(shutil.which(tool))
    payload = _agy_payload(tmp_path, tmp_path / "x.py")
    result = _run_hook("ruff-format.sh", payload, tmp_path, bin_dir, path=str(bin_dir))
    assert result.returncode == 0
    assert "jq not found" in result.stderr
    assert result.stdout == "{}\n"  # agy still gets its answer


# ── Bash output guard (always deployed for Claude Code) ──

GUARD = Path(__file__).parent.parent / "cli" / "claude" / "hooks" / "bash-output-guard.py"


def test_settings_always_cap_output_and_guard_cat():
    for hooks in ([], list(HOOK_SCRIPTS)):
        settings = generate_settings_json(hooks, [])
        assert settings["bashOutputMaxChars"] == 16_000
        pre = settings["hooks"]["PreToolUse"]
        assert [e["matcher"] for e in pre] == ["Bash"]
        assert pre[0]["hooks"][0]["command"] == \
            '"$CLAUDE_PROJECT_DIR"/.claude/hooks/bash-output-guard.py'
    assert len(generate_settings_json(list(HOOK_SCRIPTS), [])["hooks"]["PostToolUse"]) == \
        len(HOOK_SCRIPTS)


def test_guard_deployed_even_without_selected_hooks(tmp_path: Path):
    from foundry.deploy import copy_hooks
    copy_hooks(tmp_path, [])
    guard = tmp_path / ".claude" / "hooks" / "bash-output-guard.py"
    assert guard.read_text() == GUARD.read_text()
    assert os.access(guard, os.X_OK)
    assert os.access(GUARD, os.X_OK)


def _guard(command: str, cwd: Path) -> str:
    event = {"tool_name": "Bash", "cwd": str(cwd), "tool_input": {"command": command}}
    proc = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), text=True,
                          capture_output=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.mark.parametrize(("command", "blocked"), [
    ("cat big.txt", True),
    ("git status && cat big.txt", True),
    ("cat small.txt; cat big.txt", True),
    ("cat small.txt", False),
    ("cat big.txt | head -20", False),
    ("cat big.txt > copy.txt", False),
    ("cat > new.txt <<'EOF'\nhi\nEOF", False),
    ("grep -n foo big.txt", False),
    ("cat missing.txt", False),
    ('cat "unbalanced', False),
])
def test_guard_blocks_only_plain_cat_of_large_files(tmp_path: Path, command: str, blocked: bool):
    (tmp_path / "big.txt").write_text("line\n" * 400)
    (tmp_path / "small.txt").write_text("line\n" * 5)
    out = _guard(command, tmp_path)
    if blocked:
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "deny"
        assert "big.txt (400 lines)" in decision["permissionDecisionReason"]
        assert "Read tool" in decision["permissionDecisionReason"]
    else:
        assert out == ""


def test_guard_ignores_malformed_input(tmp_path: Path):
    proc = subprocess.run([sys.executable, str(GUARD)], input="not json", text=True,
                          capture_output=True, timeout=30)
    assert proc.returncode == 0 and proc.stdout == ""
