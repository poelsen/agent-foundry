"""Tests for run_benchmark.py's CLI backends (command construction, no real CLI calls)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import pytest

import run_benchmark as rb


@pytest.fixture
def fake_run(monkeypatch):
    """Record subprocess.run calls; the test sets the reply via ``calls.reply``."""
    calls: list[dict] = []

    def _run(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        reply = calls.reply  # type: ignore[attr-defined]
        if callable(reply):
            reply = reply(cmd, kwargs)
        return subprocess.CompletedProcess(cmd, *reply)

    calls = type("Calls", (list,), {})()
    monkeypatch.setattr(rb.subprocess, "run", _run)
    monkeypatch.setattr(rb.shutil, "which", lambda name: f"/usr/bin/{name}")
    return calls


def test_backend_table_covers_all_clis():
    assert set(rb.BACKENDS) == {"claude", "copilot", "codex", "agy"}


def test_claude_effort_is_explicit(fake_run, monkeypatch):
    # Without BENCH_CLAUDE_EFFORT the CLI falls back to the user's settings.json,
    # so a run is only reproducible when the effort is passed explicitly. (Not
    # CLAUDE_EFFORT: Claude Code exports that into its own shells.)
    monkeypatch.delenv("BENCH_CLAUDE_EFFORT", raising=False)
    fake_run.reply = (0, json.dumps({"type": "result", "result": " hi "}), "")
    assert rb._invoke("p", "claude", "claude-sonnet-5-5") == "hi"
    assert "--effort" not in fake_run[0]["cmd"]

    monkeypatch.setenv("BENCH_CLAUDE_EFFORT", "xhigh")
    rb._invoke("p", "claude", "claude-sonnet-5-5")
    cmd = fake_run[1]["cmd"]
    assert cmd[cmd.index("--effort") + 1] == "xhigh"


def test_codex_reads_final_answer_file(fake_run, monkeypatch):
    monkeypatch.setenv("CODEX_EFFORT", "high")

    def reply(cmd, kwargs):
        Path(cmd[cmd.index("-o") + 1]).write_text("the answer\n")
        return (0, "progress noise", "")

    fake_run.reply = reply
    assert rb._invoke("long prompt", "codex", "gpt-6.1-sol") == "the answer"
    call = fake_run[0]
    assert call["cmd"][:2] == ["/usr/bin/codex", "exec"]
    assert {"-s", "read-only", "--skip-git-repo-check", "--ephemeral"} <= set(call["cmd"])
    assert call["cmd"][call["cmd"].index("-m") + 1] == "gpt-6.1-sol"
    assert 'model_reasoning_effort="high"' in call["cmd"]
    assert call["input"] == "long prompt"         # prompt on stdin, not argv
    assert "long prompt" not in call["cmd"]


def test_explicit_effort_overrides_env_per_call(fake_run, monkeypatch):
    # Subject and judge can share a backend (codex subject at high, codex judge
    # at xhigh), so the effort is passed per call and beats the env var.
    monkeypatch.setenv("CODEX_EFFORT", "low")

    def reply(cmd, kwargs):
        Path(cmd[cmd.index("-o") + 1]).write_text("a")
        return (0, "", "")

    fake_run.reply = reply
    rb._invoke("p", "codex", "gpt-6.1-sol", effort="high")
    rb._invoke("p", "codex", "gpt-6.1-sol", effort="xhigh")
    rb._invoke("p", "codex", "gpt-6.1-sol")
    efforts = [next(a for a in c["cmd"] if a.startswith("model_reasoning_effort")) for c in fake_run]
    assert efforts == ['model_reasoning_effort="high"', 'model_reasoning_effort="xhigh"',
                       'model_reasoning_effort="low"']


def test_copilot_effort_flag(fake_run):
    fake_run.reply = (0, "ok", "")
    rb._invoke("p", "copilot", "some-model", effort="high")
    cmd = fake_run[0]["cmd"]
    assert cmd[cmd.index("--reasoning-effort") + 1] == "high"


def test_codex_failure_raises(fake_run):
    fake_run.reply = (1, "", "auth error")
    with pytest.raises(RuntimeError, match="auth error"):
        rb._invoke("p", "codex", "gpt-6.1-sol")


def test_agy_parses_json_response(fake_run, monkeypatch):
    monkeypatch.setenv("AGY_EFFORT", "low")
    fake_run.reply = (0, json.dumps({"status": "SUCCESS", "response": " hi \n"}), "")
    assert rb._invoke("prompt", "agy", "gemini-3.1-pro-high") == "hi"
    cmd = fake_run[0]["cmd"]
    assert cmd[:3] == ["/usr/bin/agy", "-p", "prompt"]
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--model") + 1] == "gemini-3.1-pro-high"
    assert cmd[cmd.index("--effort") + 1] == "low"
    assert fake_run[0]["stdin"] == subprocess.DEVNULL  # never waits on stdin


def test_agy_api_error_raises(fake_run):
    fake_run.reply = (3, json.dumps({"status": "ERROR", "error": "503 unavailable"}), "")
    with pytest.raises(RuntimeError, match="503 unavailable"):
        rb._invoke("p", "agy", "gemini-3.8-flash-low")


def test_agy_denied_tool_with_empty_response_raises(fake_run):
    # Headless agy auto-denies tools that need approval and can then answer with
    # nothing while still reporting SUCCESS; that must never be scored as a reply.
    denied = {"status": "SUCCESS", "response": "",
              "denied_actions": [{"action": "command", "display_name": "RunCommand"}]}
    fake_run.reply = (0, json.dumps(denied), "jetski: no output produced")
    with pytest.raises(RuntimeError, match="no output produced"):
        rb._invoke("p", "agy", "gemini-3.8-flash-high")


def test_agy_skip_permissions_is_opt_in(fake_run, monkeypatch):
    fake_run.reply = (0, json.dumps({"status": "SUCCESS", "response": "ok"}), "")
    rb._invoke("p", "agy", "gemini-3.8-flash-high")
    assert "--dangerously-skip-permissions" not in fake_run[0]["cmd"]

    monkeypatch.setenv("AGY_SKIP_PERMISSIONS", "1")
    rb._invoke("p", "agy", "gemini-3.8-flash-high")
    assert "--dangerously-skip-permissions" in fake_run[1]["cmd"]


def test_results_json_records_errored_runs():
    # An errored combo has no EvalResult; without a count the mode's average
    # silently covers fewer runs than the other modes.
    from eval_rubric import load_challenge
    challenge = load_challenge(rb.CHALLENGES_DIR / "scope-001.yaml")
    all_results = {challenge.id: {"baseline": []}}
    errors = {challenge.id: {"baseline": ["agy CLI gave no answer"]}}
    data = rb.results_to_json([challenge], all_results, [None], errors)
    assert data["challenges"][challenge.id]["modes"]["baseline"]["errors"] == ["agy CLI gave no answer"]
    clean = rb.results_to_json([challenge], all_results, [None])
    assert "errors" not in clean["challenges"][challenge.id]["modes"]["baseline"]


def test_results_json_records_outcomes():
    # Outcomes are the process-blind signal; they used to be printed only.
    from eval_rubric import OutcomeScore, load_challenge, score_response
    challenge = load_challenge(rb.CHALLENGES_DIR / "adversarial-013.yaml")
    oids = list(challenge.rubric.outcome_elements)
    result = score_response(challenge, [], [], outcome_scores=[
        OutcomeScore(oids[0], True), OutcomeScore(oids[1], False)])
    data = rb.results_to_json([challenge], {challenge.id: {"baseline": [result]}}, [None])
    outcomes = data["challenges"][challenge.id]["modes"]["baseline"]["outcomes"]
    assert outcomes == {oids[0]: {"hits": 1, "total": 1}, oids[1]: {"hits": 0, "total": 1}}


def test_every_backend_has_its_own_default_model():
    assert set(rb.DEFAULT_MODELS) == set(rb.BACKENDS)
    assert rb.DEFAULT_MODELS["codex"] == "gpt-6.1-sol"
