"""Tests for the delegate skill's runner (cli/claude/skills/delegate/scripts/delegate.py).

Unit tests cover command building, output parsing, environment handling and
policy. End-to-end tests run the real script against a temporary git
repository, with tests/fixtures/fake_agent_cli.py standing in for the four
target CLIs.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "cli" / "claude" / "skills" / "delegate" / "scripts" / "delegate.py"
FAKE_CLI = ROOT / "tests" / "fixtures" / "fake_agent_cli.py"

# No __pycache__ next to the script: the skill directory is deployed as-is.
_write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
_loader_spec = importlib.util.spec_from_file_location("delegate", SCRIPT)
delegate = importlib.util.module_from_spec(_loader_spec)
_loader_spec.loader.exec_module(delegate)
sys.dont_write_bytecode = _write_bytecode

GIT_ID = ["-c", "user.name=tester", "-c", "user.email=t@example.com"]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *GIT_ID, *args], cwd=repo, check=True, text=True,
                          capture_output=True).stdout.strip()


def _spec(target: str, mode: str = "write", **extra) -> dict:
    return {"target": target, "mode": mode, "workdir": "/work", **extra}


# ── command building ──


def test_claude_write_skips_permissions_but_denies_push(tmp_path: Path):
    cmd = delegate.build_command(_spec("claude"), "task", tmp_path)
    assert "--dangerously-skip-permissions" in cmd["argv"]
    assert "Bash(git push:*)" in cmd["argv"]
    assert cmd["stdin"] == "task"  # prompt on stdin, no argv size limit


def test_claude_read_only_denies_edit_tools(tmp_path: Path):
    argv = delegate.build_command(_spec("claude", "read-only"), "t", tmp_path)["argv"]
    assert "--dangerously-skip-permissions" not in argv
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "Edit,Write,NotebookEdit" in argv[argv.index("--disallowedTools") + 1]


@pytest.mark.parametrize(("mode", "sandbox"), [("write", "workspace-write"),
                                              ("read-only", "read-only")])
def test_codex_uses_its_sandbox_by_default(tmp_path: Path, mode: str, sandbox: str):
    argv = delegate.build_command(_spec("codex", mode), "t", tmp_path)["argv"]
    assert f'sandbox_mode="{sandbox}"' in argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert argv[argv.index("-o") + 1] == str(tmp_path / "final.txt")


def test_codex_bypass_and_network_are_policy_driven(tmp_path: Path):
    bypass = delegate.build_command(_spec("codex", codex_sandbox="bypass"), "t", tmp_path)
    assert "--dangerously-bypass-approvals-and-sandbox" in bypass["argv"]
    net = delegate.build_command(_spec("codex", codex_network=True), "t", tmp_path)
    assert "sandbox_workspace_write.network_access=true" in net["argv"]


def test_codex_resume_reads_prompt_from_stdin(tmp_path: Path):
    argv = delegate.build_command(_spec("codex", resume="thr-1"), "t", tmp_path)["argv"]
    assert argv[:3] == ["codex", "exec", "resume"]
    assert argv[-2:] == ["thr-1", "-"]


def test_agy_gets_the_workspace_and_write_approval_only_in_write_mode(tmp_path: Path):
    write = delegate.build_command(_spec("agy"), "t", tmp_path)["argv"]
    assert write[write.index("--add-dir") + 1] == "/work"
    assert "--dangerously-skip-permissions" in write
    ro = delegate.build_command(_spec("agy", "read-only"), "t", tmp_path)["argv"]
    assert "--dangerously-skip-permissions" not in ro


def test_copilot_read_only_denies_write_and_shell(tmp_path: Path):
    argv = delegate.build_command(_spec("copilot", "read-only"), "t", tmp_path)["argv"]
    denied = [argv[i + 1] for i, a in enumerate(argv) if a == "--deny-tool"]
    assert denied == ["write", "shell"]
    write = delegate.build_command(_spec("copilot"), "t", tmp_path)["argv"]
    assert [write[i + 1] for i, a in enumerate(write) if a == "--deny-tool"] == [
        "shell(git push)"]


@pytest.mark.parametrize("target", ["agy", "copilot"])
def test_long_prompt_passed_as_a_file_pointer(tmp_path: Path, target: str):
    prompt = "x" * (delegate.ARGV_PROMPT_CAP + 1)
    argv = delegate.build_command(_spec(target), prompt, tmp_path)["argv"]
    text = argv[argv.index("-p") + 1]
    assert str(tmp_path / "prompt.md") in text and len(text) < 500
    assert str(tmp_path) in argv  # the run dir is readable by the target


def test_model_and_effort_passed_through(tmp_path: Path):
    argv = delegate.build_command(_spec("codex", model="gpt-5.5", effort="high"), "t",
                                  tmp_path)["argv"]
    assert argv[argv.index("-m") + 1] == "gpt-5.5"
    assert 'model_reasoning_effort="high"' in argv


def test_prompt_preamble_scopes_the_delegate():
    ctx = {"host": "claude", "target": "codex", "cli": "codex", "job": "j", "mode": "write",
           "workdir": "/wt", "branch": "delegate/j", "may_delegate": False}
    text = delegate.compose_prompt("Fix the bug", ctx)
    assert "/wt" in text and "delegate/j" in text and "Do not push" in text
    assert "don't need to commit" in text
    assert "Do not hand this task" in text
    assert text.rstrip().endswith("Fix the bug")
    ro = delegate.compose_prompt("Review", {**ctx, "mode": "read-only", "may_delegate": True})
    assert "read-only" in ro and "Do not hand" not in ro
    agy = delegate.compose_prompt("Review", {**ctx, "cli": "agy", "mode": "read-only"})
    assert "Shell commands are disabled" in agy and "disabled" not in ro


def test_auto_commit_leaves_build_artifacts_out(world):
    code, out = world.run("run", "--to", "claude", "--job", "art", "--task", "t",
                          FAKE_CLI_ACTION="artifacts")
    assert code == 0, out
    assert out["files_changed"] == ["delegated.txt"]
    assert any("1 build artifact" in w for w in out["warnings"])


def test_model_used_reported_when_the_cli_says(tmp_path: Path):
    out = "\n".join(json.dumps(e) for e in (
        {"type": "assistant.message", "data": {"content": "done", "model": "gpt-5.6-luna"}},
        {"type": "result", "sessionId": "s", "exitCode": 0}))
    assert delegate.parse_output("copilot", out, "", tmp_path)["model_used"] == "gpt-5.6-luna"
    claude = json.dumps({"result": "ok", "modelUsage": {"claude-opus-5-5": {}}})
    assert delegate.parse_output("claude", claude, "", tmp_path)["model_used"] == \
        "claude-opus-5-5"


# ── output parsing ──


def test_parse_claude_result(tmp_path: Path):
    out = json.dumps({"type": "result", "result": "done", "session_id": "s1",
                      "is_error": False, "total_cost_usd": 0.1, "num_turns": 3,
                      "permission_denials": [{"tool_name": "Bash"}]})
    res = delegate.parse_output("claude", out, "", tmp_path / "none")
    assert res["summary"] == "done" and res["session_id"] == "s1" and not res["error"]
    assert res["usage"]["permission_denials"] == 1


def test_parse_codex_events_and_final_file(tmp_path: Path):
    final = tmp_path / "final.txt"
    final.write_text("PONG\n")
    out = "\n".join(json.dumps(e) for e in (
        {"type": "thread.started", "thread_id": "t1"},
        {"type": "turn.completed", "usage": {"input_tokens": 3}}))
    res = delegate.parse_output("codex", out, "Reading additional input from stdin...", final)
    assert res == {"summary": "PONG", "session_id": "t1", "usage": {"input_tokens": 3},
                   "error": None, "model_used": None}


def test_parse_agy_empty_response_is_an_error(tmp_path: Path):
    out = json.dumps({"conversation_id": "c1", "status": "SUCCESS", "response": "",
                      "usage": "{'input_tokens': 11908}",
                      "denied_actions": "[{'action': 'command'}]"})
    res = delegate.parse_output("agy", out, "jetski: no output produced", tmp_path / "x")
    assert res["error"] == "jetski: no output produced"
    assert res["usage"]["input_tokens"] == 11908
    assert res["usage"]["denied_actions"] == [{"action": "command"}]


def test_parse_copilot_takes_last_non_empty_message(tmp_path: Path):
    out = "\n".join(json.dumps(e) for e in (
        {"type": "assistant.message", "data": {"content": "first"}},
        {"type": "assistant.message", "data": {"content": ""}},
        {"type": "assistant.message", "data": {"content": "final answer"}},
        {"type": "result", "sessionId": "cs", "exitCode": 0, "usage": {"premiumRequests": 1}}))
    res = delegate.parse_output("copilot", out, "", tmp_path / "x")
    assert res["summary"] == "final answer" and res["session_id"] == "cs"


# ── environment ──


PARENT_ENV = {
    "PATH": "/bin", "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_TOKEN": "secret",
    "CLAUDE_CODE_SESSION_ID": "s", "CLAUDE_CODE_USE_BEDROCK": "1",
    "CLAUDE_CONFIG_DIR": "/c", "CODEX_THREAD_ID": "t", "CODEX_HOME": "/h",
    "ANTIGRAVITY_CSRF_TOKEN": "x", "COPILOT_CLI": "1", "AI_AGENT": "claude-code",
    "FOUNDRY_DELEGATE_DEPTH": "0", "ANTHROPIC_API_KEY": "sk-ant",
    "CLAUDE_CODE_OAUTH_TOKEN": "oauth", "ANTHROPIC_CUSTOM_HEADERS": "X-Org: 1",
    "OPENAI_API_KEY": "sk-oai", "GEMINI_API_KEY": "g",
}


def test_child_env_keeps_only_the_targets_own_credentials():
    env = delegate.child_env(PARENT_ENV, "claude", {"FOUNDRY_DELEGATE_DEPTH": "1"})
    assert env == {"PATH": "/bin", "CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CONFIG_DIR": "/c",
                   "CODEX_HOME": "/h", "FOUNDRY_DELEGATE_DEPTH": "1",
                   "ANTHROPIC_API_KEY": "sk-ant", "CLAUDE_CODE_OAUTH_TOKEN": "oauth",
                   "ANTHROPIC_CUSTOM_HEADERS": "X-Org: 1"}
    codex = delegate.child_env(PARENT_ENV, "codex")
    assert codex["OPENAI_API_KEY"] == "sk-oai"
    assert not {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "GEMINI_API_KEY"} & set(codex)
    passed = delegate.child_env(PARENT_ENV, "codex", pass_env=["GEMINI_API_KEY"])
    assert passed["GEMINI_API_KEY"] == "g"


def _policy_error(raw: dict) -> str:
    with pytest.raises(delegate.DelegateError) as e:
        delegate.validate_policy(raw)
    return str(e.value)


@pytest.mark.parametrize(("raw", "fragment"), [
    ({"max_depht": 3}, "unknown keys"),
    ({"allow_write": "false"}, "allow_write must be bool"),
    ({"max_depth": True}, "max_depth must be int"),
    ({"max_concurrent": 0}, "max_concurrent must be >= 1"),
    ({"targets": {"copilot": {"enable": False}}}, "targets.copilot.enable"),
    ({"targets": {"codex": {"sandbox": "off"}}}, "targets.codex.sandbox"),
    ({"targets": {"gemini": {}}}, "targets.gemini"),
    ({"pass_env": ["OK", "not ok"]}, "pass_env"),
    ({"profiles": {}}, "unknown keys"),
])
def test_policy_validation_fails_closed(raw: dict, fragment: str):
    assert fragment in _policy_error(raw)


def test_valid_policy_passes():
    delegate.validate_policy({
        "allow_write": False, "max_depth": 2, "pass_env": ["GH_TOKEN"],
        "targets": {"codex": {"sandbox": "bypass", "model": "gpt-5.5"}},
    })


@pytest.mark.parametrize(("env", "host"), [
    ({"CLAUDECODE": "1"}, "claude"),
    ({"CLAUDECODE": "1", "CODEX_THREAD_ID": "t"}, "codex"),  # launched from a Claude shell
    ({"ANTIGRAVITY_AGENT": "1"}, "agy"),
    ({"COPILOT_CLI": "1"}, "copilot"),
    ({"CLAUDECODE": "1", "FOUNDRY_DELEGATE_TARGET": "agy"}, "agy"),  # inside a delegate
    ({}, "shell"),
])
def test_detect_host(env: dict, host: str):
    assert delegate.detect_host(env) == host


# ── end-to-end with fake CLIs ──


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    """A git repo, fake target CLIs on PATH, and a clean delegate environment."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in delegate.TARGETS:
        wrapper = bin_dir / name
        wrapper.write_text(
            f"#!/bin/sh\nFAKE_CLI_NAME={name} exec {sys.executable} {FAKE_CLI} \"$@\"\n")
        wrapper.chmod(0o755)
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "app.py").write_text("print('hi')\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init")
    record = tmp_path / "calls.jsonl"
    env = {k: v for k, v in os.environ.items()
           if not delegate.SESSION_ENV_PATTERN.match(k) and k not in delegate.SESSION_ENV
           and k != "ANTHROPIC_API_KEY"}
    env.update(PATH=f"{bin_dir}:{env['PATH']}", FAKE_CLI_RECORD=str(record),
               GIT_AUTHOR_NAME="tester", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="tester", GIT_COMMITTER_EMAIL="t@example.com",
               CLAUDECODE="1", CLAUDE_CODE_MESSAGING_TOKEN="parent-secret")

    class World:
        def __init__(self):
            self.repo, self.env, self.record, self.tmp = repo, env, record, tmp_path

        def run(self, *args: str, cwd: Path | None = None, **env_extra) -> tuple[int, dict]:
            proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or repo,
                                  env={**self.env, **env_extra}, text=True,
                                  capture_output=True, timeout=120)
            try:
                out = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
            except ValueError:
                out = {"raw": proc.stdout}
            out.setdefault("_stderr", proc.stderr)
            out.setdefault("_stdout", proc.stdout)
            return proc.returncode, out

        def calls(self) -> list[dict]:
            if not record.exists():
                return []
            return [json.loads(line) for line in record.read_text().splitlines()]

        def policy(self, **policy):
            (repo / ".delegate").mkdir(exist_ok=True)
            (repo / ".delegate" / "policy.json").write_text(json.dumps(policy))

    return World()


def _wt(world, job: str) -> Path:
    return world.repo.parent / f"proj-delegate-{job}"


@pytest.mark.parametrize("target", delegate.TARGETS)
def test_write_run_commits_on_the_job_branch(world, target: str):
    code, out = world.run("run", "--to", target, "--job", f"j-{target}", "--task", "add a file")
    assert code == 0, out
    assert out["status"] == "succeeded"
    assert out["summary"] == f"{target} finished the task"
    assert out["files_changed"] == ["delegated.txt"] and out["commits"] == 1
    wt = _wt(world, f"j-{target}")
    assert Path(out["workdir"]) == wt and (wt / "delegated.txt").exists()
    assert not (world.repo / "delegated.txt").exists()  # nothing reaches the caller yet
    assert _git(world.repo, "log", "-1", "--format=%an", f"delegate/j-{target}") \
        == f"delegate ({target})"
    call = world.calls()[-1]
    assert call["cwd"] == str(wt)
    assert call["env"]["FOUNDRY_DELEGATE_DEPTH"] == "1"
    assert call["env"]["FOUNDRY_DELEGATE_CHAIN"] == f"claude>{target}"
    assert call["env"]["FOUNDRY_DELEGATE_TARGET"] == target
    assert "CLAUDECODE" not in call["env"]
    assert "CLAUDE_CODE_MESSAGING_TOKEN" not in call["env"]
    assert "add a file" in call["prompt"] and "Do not push" in call["prompt"]
    assert out["session_id"]


def test_state_lives_in_the_git_dir(world):
    world.run("run", "--to", "codex", "--job", "ign", "--task", "t")
    assert _git(world.repo, "status", "--porcelain") == ""
    assert (world.repo / ".git" / "delegate" / "jobs" / "ign" / "job.json").is_file()
    assert not (world.repo / ".delegate").exists()
    log = (world.repo / ".git" / "delegate" / "log.jsonl").read_text().splitlines()
    assert [json.loads(line)["event"] for line in log] == ["start", "end"]


def test_merge_then_discard(world):
    world.run("run", "--to", "claude", "--job", "m", "--task", "t")
    code, out = world.run("merge", "m")
    assert code == 0 and out["merged"], out
    assert (world.repo / "delegated.txt").exists()
    assert "Merge delegate/m (delegated to claude)" in _git(world.repo, "log", "-1", "--format=%s")
    code, out = world.run("discard", "m")
    assert code == 0, out
    assert not _wt(world, "m").exists()
    assert not _git(world.repo, "branch", "--list", "delegate/m")


def test_discard_refuses_unmerged_work_without_force(world):
    world.run("run", "--to", "claude", "--job", "d", "--task", "t")
    code, out = world.run("discard", "d")
    assert code == delegate.EXIT_CONFIRM and "unmerged" in out["error"]
    assert _wt(world, "d").exists()
    code, _ = world.run("discard", "d", "--force")
    assert code == 0 and not _wt(world, "d").exists()


def test_delegate_that_commits_itself(world):
    code, out = world.run("run", "--to", "codex", "--job", "c", "--task", "t",
                          FAKE_CLI_ACTION="commit")
    assert code == 0 and out["commits"] == 1 and out["files_changed"] == ["delegated.txt"]
    assert out["warnings"] == []


def test_branch_switch_is_flagged_and_not_auto_committed(world):
    code, out = world.run("run", "--to", "claude", "--job", "sw", "--task", "t",
                          FAKE_CLI_ACTION="checkout")
    assert code == 0
    assert any("instead of delegate/sw" in w for w in out["warnings"]), out
    assert any("created refs/heads/sneaky" in w for w in out["warnings"])
    assert out["commits"] == 0


def test_failed_run_reports_error(world):
    code, out = world.run("run", "--to", "agy", "--job", "f", "--task", "t",
                          FAKE_CLI_ACTION="fail")
    assert code == delegate.EXIT_FAILED and out["status"] == "failed"
    assert out["exit_code"] == 1


def test_agy_empty_response_fails(world):
    code, out = world.run("run", "--to", "agy", "--mode", "read-only", "--task", "t",
                          FAKE_CLI_ACTION="none")
    assert code == delegate.EXIT_FAILED and out["status"] == "failed" and "no output produced" in out["error"]


def test_read_only_runs_in_place_and_flags_writes(world):
    code, out = world.run("run", "--to", "copilot", "--mode", "read-only", "--task", "review")
    assert code == 0 and out["status"] == "succeeded" and out["workdir"] == str(world.repo)
    assert out["files_changed"] == ["delegated.txt"]
    assert any("1 file(s) changed in" in w and "read-only" in w for w in out["warnings"])
    assert out["branch"] is None


def test_read_only_clean_run_ignores_preexisting_dirt(world):
    (world.repo / "app.py").write_text("print('dirty')\n")
    code, out = world.run("run", "--to", "claude", "--mode", "read-only", "--task", "t",
                          FAKE_CLI_ACTION="none")
    assert code == 0 and out["warnings"] == [] and out["files_changed"] == []


def test_timeout_kills_the_target(world):
    started = time.monotonic()
    code, out = world.run("run", "--to", "claude", "--job", "slow", "--timeout", "2",
                          "--task", "t", FAKE_CLI_ACTION="sleep", FAKE_CLI_SLEEP="60")
    assert out["status"] == "timeout" and code == delegate.EXIT_FAILED
    assert time.monotonic() - started < 30


def _wait_for(pred, timeout: float = 20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.2)
    return False


def test_start_then_wait(world):
    code, out = world.run("start", "--to", "codex", "--job", "bg", "--task", "t")
    assert code == 0 and out["status"] == "running"
    code, out = world.run("wait", "bg", "--timeout", "60")
    assert code == 0 and out["status"] == "succeeded" and out["files_changed"]


def test_wait_times_out_while_running(world):
    world.run("start", "--to", "codex", "--job", "w", "--task", "t",
              FAKE_CLI_ACTION="sleep", FAKE_CLI_SLEEP="60")
    code, out = world.run("wait", "w", "--timeout", "1")
    assert code == delegate.EXIT_RUNNING and "still running" in out["note"]
    code, out = world.run("cancel", "w")
    assert out["status"] == "cancelled", out


def test_concurrency_limit(world):
    world.policy(max_concurrent=1)
    world.run("start", "--to", "claude", "--job", "a", "--task", "t",
              FAKE_CLI_ACTION="sleep", FAKE_CLI_SLEEP="60")
    code, out = world.run("start", "--to", "claude", "--job", "b", "--task", "t")
    assert code == delegate.EXIT_REFUSED and "max_concurrent" in out["error"]
    world.run("cancel", "a")


def test_depth_limit_blocks_nested_delegation(world):
    code, out = world.run("run", "--to", "codex", "--task", "t", FOUNDRY_DELEGATE_DEPTH="1")
    assert code == delegate.EXIT_REFUSED and "depth limit" in out["error"]
    world.policy(max_depth=2)
    code, out = world.run("run", "--to", "codex", "--job", "nested", "--task", "t",
                          FOUNDRY_DELEGATE_DEPTH="1", FOUNDRY_DELEGATE_CHAIN="claude>agy",
                          FOUNDRY_DELEGATE_TARGET="agy")
    assert code == 0, out
    assert out["host"] == "agy" and out["chain"] == "claude>agy>codex"
    assert "Do not hand this task" in world.calls()[-1]["prompt"]  # depth 2 is the max


def test_policy_refusals(world):
    world.policy(allow_write=False, targets={"agy": {"enabled": False}}, max_timeout_s=60)
    assert world.run("run", "--to", "claude", "--task", "t")[0] == delegate.EXIT_REFUSED
    code, out = world.run("run", "--to", "agy", "--mode", "read-only", "--task", "t")
    assert code == delegate.EXIT_REFUSED and "disabled" in out["error"]
    code, out = world.run("run", "--to", "claude", "--mode", "read-only", "--timeout", "61",
                          "--task", "t")
    assert code == delegate.EXIT_REFUSED and "max_timeout_s" in out["error"]
    assert world.calls() == []


def test_unknown_policy_key_rejected(world):
    world.policy(max_depht=3)
    code, out = world.run("run", "--to", "claude", "--task", "t")
    assert code == delegate.EXIT_USAGE and "max_depht" in out["error"]


def test_refused_inside_codex_sandbox(world):
    code, out = world.run("run", "--to", "claude", "--task", "t",
                          CODEX_SANDBOX_NETWORK_DISABLED="1")
    assert code == delegate.EXIT_REFUSED and "escalated" in out["error"]


def test_missing_cli_is_unavailable(world):
    (world.tmp / "bin" / "agy").unlink()
    code, out = world.run("run", "--to", "agy", "--task", "t",
                          PATH=f"{world.tmp / 'bin'}:/usr/bin:/bin")
    assert code == delegate.EXIT_UNAVAILABLE and "not installed" in out["error"]


def test_follow_up_resumes_the_session(world):
    world.run("run", "--to", "claude", "--job", "fu", "--task", "first")
    code, out = world.run("run", "--job", "fu", "--resume", "--task", "second")
    assert code == 0 and out["run"] == 2, out
    argv = world.calls()[-1]["argv"]
    assert argv[argv.index("--resume") + 1] == "sess-claude"
    assert world.calls()[-1]["cwd"] == str(_wt(world, "fu"))


def test_follow_up_cannot_switch_target(world):
    world.run("run", "--to", "claude", "--job", "sw2", "--task", "first")
    code, out = world.run("run", "--to", "codex", "--job", "sw2", "--task", "second")
    assert code == delegate.EXIT_USAGE and "belongs to claude" in out["error"]


def test_include_dirty_snapshot_and_merge_applies_delta(world):
    (world.repo / "app.py").write_text("print('work in progress')\n")
    (world.repo / "new.py").write_text("x = 1\n")
    code, out = world.run("run", "--to", "claude", "--job", "dirty", "--include-dirty",
                          "--task", "t")
    assert code == 0, out
    wt = _wt(world, "dirty")
    assert (wt / "app.py").read_text() == "print('work in progress')\n"
    assert (wt / "new.py").exists()
    assert out["files_changed"] == ["delegated.txt"]  # only the delegate's own change
    code, out = world.run("merge", "dirty")
    assert code == 0 and "working tree" in out["how"], out
    assert (world.repo / "delegated.txt").exists()
    assert (world.repo / "app.py").read_text() == "print('work in progress')\n"
    assert _git(world.repo, "log", "--format=%s") == "init"  # nothing committed for the user


def test_dirty_tree_without_include_dirty_is_noted(world):
    (world.repo / "app.py").write_text("print('wip')\n")
    code, out = world.run("run", "--to", "claude", "--job", "nd", "--task", "t")
    assert code == 0
    assert "not visible to the delegate" in out["base_note"]
    assert (_wt(world, "nd") / "app.py").read_text() == "print('hi')\n"


def test_called_from_a_worktree_shares_the_registry(world):
    world.run("run", "--to", "claude", "--job", "outer", "--task", "t")
    code, out = world.run("list", "--json", cwd=_wt(world, "outer"))
    assert code == 0
    assert [j["job"] for j in out["jobs"]] == ["outer"]


def test_existing_job_name_or_branch_rejected(world):
    _git(world.repo, "branch", "delegate/taken")
    code, out = world.run("run", "--to", "claude", "--job", "taken", "--task", "t")
    assert code == delegate.EXIT_USAGE and "already exists" in out["error"]
    code, out = world.run("run", "--to", "claude", "--job", "Bad Name", "--task", "t")
    assert code == delegate.EXIT_USAGE and "invalid job name" in out["error"]


def test_shell_refuses_without_a_terminal(world):
    code, out = world.run("shell", "--job", "s", "--to", "claude")
    assert code == delegate.EXIT_REFUSED and "own terminal" in out["error"]


def test_doctor_reports_targets_and_policy(world):
    code, out = world.run("doctor")
    assert code == 0
    assert out["host"] == "claude" and out["policy_source"] == "defaults"
    assert all(out["targets"][t]["installed"] for t in delegate.TARGETS)
    assert out["targets"]["codex"]["sandbox_works"] is True
    assert out["policy"]["max_depth"] == 1


def test_list_and_log(world):
    world.run("run", "--to", "codex", "--job", "l1", "--task", "t")
    code, out = world.run("list")
    assert code == 0 and "l1" in out["_stdout"] and "succeeded" in out["_stdout"]
    code, out = world.run("log", "l1")
    assert "thread.started" in out["_stdout"]


def test_task_from_stdin(world):
    proc = subprocess.run([sys.executable, str(SCRIPT), "run", "--to", "claude", "--job", "si",
                           "--task-file", "-"], cwd=world.repo, env=world.env, text=True,
                          input="task from stdin", capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stdout
    assert "task from stdin" in world.calls()[-1]["prompt"]


def test_empty_task_rejected(world):
    code, out = world.run("run", "--to", "claude", "--task", "  ")
    assert code == delegate.EXIT_USAGE and "empty" in out["error"]


def test_not_a_git_repo(tmp_path: Path, world):
    code, out = world.run("list", cwd=tmp_path)
    assert code == delegate.EXIT_USAGE and "not inside a git repository" in out["error"]


def test_lost_supervisor_detected(world):
    world.run("run", "--to", "claude", "--job", "lost", "--task", "t")
    job_file = world.repo / ".git" / "delegate" / "jobs" / "lost" / "job.json"
    rec = json.loads(job_file.read_text())
    rec["runs"][-1].update(status="running", started_ts=time.time() - 3600)
    job_file.write_text(json.dumps(rec))  # its supervisor has long exited
    code, out = world.run("status", "lost")
    assert code == delegate.EXIT_FAILED and out["status"] == "lost"


def test_script_needs_only_the_stdlib():
    tree = __import__("ast").parse(SCRIPT.read_text())
    imported = {n.names[0].name.split(".")[0] for n in tree.body
                if isinstance(n, __import__("ast").Import)}
    imported |= {n.module.split(".")[0] for n in tree.body
                 if isinstance(n, __import__("ast").ImportFrom) and n.module}
    assert imported <= set(sys.stdlib_module_names)


def test_script_is_executable():
    assert os.access(SCRIPT, os.X_OK)
    assert shutil.which("git")


# ── regressions from review ──


def _job(world, job: str) -> dict:
    return json.loads((world.repo / ".git" / "delegate" / "jobs" / job / "job.json").read_text())


def _group_alive(pgid: int) -> bool:
    return bool(delegate.group_members(pgid))


def test_killed_supervisor_takes_the_target_with_it(world):
    world.run("start", "--to", "claude", "--job", "k9", "--task", "t",
              FAKE_CLI_ACTION="sleep", FAKE_CLI_SLEEP="60")
    assert _wait_for(lambda: _job(world, "k9")["runs"][-1].get("child_pgid"))
    run = _job(world, "k9")["runs"][-1]
    os.kill(run["supervisor_pid"], 9)
    assert _wait_for(lambda: not _group_alive(run["child_pgid"]))
    code, out = world.run("status", "k9")
    assert code == delegate.EXIT_FAILED and out["status"] == "lost"


def test_slow_supervisor_is_not_declared_lost(world):
    world.run("start", "--to", "claude", "--job", "slow2", "--task", "t",
              FAKE_CLI_ACTION="sleep", FAKE_CLI_SLEEP="60")
    job_file = world.repo / ".git" / "delegate" / "jobs" / "slow2" / "job.json"
    assert _wait_for(lambda: _job(world, "slow2")["runs"][-1].get("child_pgid"))
    code, out = world.run("status", "slow2")
    assert code == delegate.EXIT_RUNNING and out["status"] == "running"
    code, out = world.run("run", "--job", "slow2", "--task", "again")
    assert code == delegate.EXIT_RUNNING and "still running" in out["error"]
    assert json.loads(job_file.read_text())["runs"][-1]["run"] == 1
    world.run("cancel", "slow2")


def test_cancel_escalates_when_the_target_ignores_sigterm(world):
    world.run("start", "--to", "codex", "--job", "stub", "--task", "t",
              FAKE_CLI_ACTION="stubborn", FAKE_CLI_SLEEP="120")
    assert _wait_for(lambda: _job(world, "stub")["runs"][-1].get("child_pgid"))
    pgid = _job(world, "stub")["runs"][-1]["child_pgid"]
    time.sleep(1)  # let the fake install its SIGTERM trap
    started = time.monotonic()
    code, out = world.run("cancel", "stub")
    assert code == delegate.EXIT_FAILED and out["status"] == "cancelled", out
    assert time.monotonic() - started < delegate.KILL_GRACE_S + 15
    assert not _group_alive(pgid)


def test_background_children_are_swept_after_the_run(world):
    code, out = world.run("run", "--to", "claude", "--job", "bgkid", "--task", "t",
                          FAKE_CLI_ACTION="background")
    assert code == 0, out
    pgid = _job(world, "bgkid")["runs"][-1]["child_pgid"]
    assert _wait_for(lambda: not _group_alive(pgid), 10)


def test_discard_after_merge_protects_a_follow_up(world):
    world.run("run", "--to", "claude", "--job", "fm", "--task", "first")
    assert world.run("merge", "fm")[0] == 0
    code, out = world.run("run", "--job", "fm", "--task", "second",
                          FAKE_CLI_ACTION="commit2")
    assert code == 0 and out["files_changed"] == ["second.txt"], out  # this run's own change
    assert any("merge fm" in step for step in out["next"])
    code, out = world.run("discard", "fm")
    assert code == delegate.EXIT_CONFIRM and "1 unmerged commit" in out["error"]
    assert world.run("merge", "fm")[0] == 0
    assert (world.repo / "second.txt").exists()
    assert world.run("discard", "fm")[0] == 0


def test_discard_refuses_uncommitted_worktree_changes(world):
    world.run("run", "--to", "claude", "--job", "uc", "--task", "t", FAKE_CLI_ACTION="none")
    (_wt(world, "uc") / "hand-edit.txt").write_text("operator work\n")
    code, out = world.run("discard", "uc")
    assert code == delegate.EXIT_CONFIRM and "uncommitted" in out["error"]
    assert world.run("discard", "uc", "--force")[0] == 0


def test_read_only_codex_refused_when_its_sandbox_is_bypassed(world):
    world.policy(targets={"codex": {"sandbox": "bypass"}})
    code, out = world.run("run", "--to", "codex", "--mode", "read-only", "--task", "t")
    assert code == delegate.EXIT_REFUSED and "write mode" in out["error"]
    code, out = world.run("run", "--to", "codex", "--job", "bp", "--task", "t")
    assert code == 0 and "--dangerously-bypass-approvals-and-sandbox" in world.calls()[-1]["argv"]


def test_failed_job_creation_leaves_nothing_behind(world):
    code, out = world.run("run", "--to", "claude", "--job", "typo", "--base", "mian",
                          "--task", "t")
    assert code == delegate.EXIT_FAILED
    assert not (world.repo / ".git" / "delegate" / "jobs" / "typo").exists()
    assert not _wt(world, "typo").exists()
    code, out = world.run("run", "--to", "claude", "--job", "typo", "--task", "t")
    assert code == 0, out


@pytest.mark.parametrize("name", ["foo.", "../../x", "a..b", "x.lock"])
def test_bad_job_names_rejected_everywhere(world, name: str):
    assert world.run("run", "--to", "claude", "--job", name, "--task", "t")[0] == \
        delegate.EXIT_USAGE
    assert world.run("discard", name)[0] == delegate.EXIT_USAGE


def test_operator_job_without_runs(world, monkeypatch):
    monkeypatch.chdir(world.repo)
    repo = delegate.Repo(world.repo)
    policy, _ = delegate.load_policy(repo)
    args = argparse.Namespace(job="op", to="codex", include_dirty=False)
    rec = delegate.operator_job(repo, policy, args)
    assert rec["runs"] == [] and _wt(world, "op").is_dir()
    code, out = world.run("status", "op")
    assert code == 0 and out["status"] == "idle"
    code, out = world.run("list", "--json")
    assert [j["job"] for j in out["jobs"]] == ["op"]
    code, out = world.run("run", "--job", "op", "--task", "t")
    assert code == 0 and out["run"] == 1 and out["target"] == "codex"
    assert world.run("discard", "op", "--force")[0] == 0


def test_merge_conflict_is_aborted_cleanly(world):
    world.run("run", "--to", "claude", "--job", "cf", "--task", "t")
    (world.repo / "delegated.txt").write_text("mine\n")
    _git(world.repo, "add", ".")
    _git(world.repo, "commit", "-qm", "conflicting")
    code, out = world.run("merge", "cf")
    assert code == delegate.EXIT_FAILED and "aborted" in out["error"]
    assert "CONFLICT" in out["error"]
    assert not (world.repo / ".git" / "MERGE_HEAD").exists()
    assert _git(world.repo, "status", "--porcelain") == ""


def test_diff_shows_base_commits_merge_would_bring(world):
    _git(world.repo, "checkout", "-qb", "feature")
    (world.repo / "feature.txt").write_text("f\n")
    _git(world.repo, "add", ".")
    _git(world.repo, "commit", "-qm", "feature work")
    _git(world.repo, "checkout", "-q", "main")
    world.run("run", "--to", "claude", "--job", "fb", "--base", "feature", "--task", "t")
    code, out = world.run("diff", "fb")
    assert code == 0
    assert "feature work" in out["_stdout"] and "feature.txt" in out["_stdout"]


def test_relative_worktree_root_from_a_subdirectory(world):
    world.policy(worktree_root="../wt-root")
    sub = world.repo / "pkg"
    sub.mkdir()
    code, out = world.run("run", "--to", "claude", "--job", "rel", "--task", "t", cwd=sub)
    assert code == 0, out
    assert Path(out["workdir"]) == (world.repo.parent / "wt-root" / "proj-delegate-rel")


def test_commit_signing_config_does_not_break_the_auto_commit(world):
    _git(world.repo, "config", "commit.gpgsign", "true")
    _git(world.repo, "config", "gpg.program", "false")
    code, out = world.run("run", "--to", "claude", "--job", "sig", "--task", "t")
    assert code == 0 and out["commits"] == 1, out
    assert out["summary"]


def test_depth_detected_from_a_running_jobs_worktree(world):
    world.run("start", "--to", "claude", "--job", "outer2", "--task", "t",
              FAKE_CLI_ACTION="sleep", FAKE_CLI_SLEEP="60")
    code, out = world.run("run", "--to", "codex", "--task", "nested", cwd=_wt(world, "outer2"))
    assert code == delegate.EXIT_REFUSED and "depth limit" in out["error"]
    world.run("cancel", "outer2")


def test_bare_repo_worktrees_share_one_registry(world, tmp_path: Path):
    bare = tmp_path / "hub.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(world.repo), str(bare)], check=True)
    one, two = tmp_path / "one", tmp_path / "two"
    subprocess.run(["git", "-C", str(bare), "worktree", "add", "-q", str(one), "main"],
                   check=True)
    subprocess.run(["git", "-C", str(bare), "worktree", "add", "-q", "-b", "b2", str(two)],
                   check=True)
    code, out = world.run("run", "--to", "claude", "--job", "hub", "--task", "t", cwd=one)
    assert code == 0, out
    code, out = world.run("list", "--json", cwd=two)
    assert [j["job"] for j in out["jobs"]] == ["hub"]
