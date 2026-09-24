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


def test_codex_reads_final_answer_file(fake_run, monkeypatch):
    monkeypatch.setenv("CODEX_EFFORT", "high")

    def reply(cmd, kwargs):
        Path(cmd[cmd.index("-o") + 1]).write_text("the answer\n")
        return (0, "progress noise", "")

    fake_run.reply = reply
    assert rb._invoke("long prompt", "codex", "gpt-5.5") == "the answer"
    call = fake_run[0]
    assert call["cmd"][:2] == ["/usr/bin/codex", "exec"]
    assert {"-s", "read-only", "--skip-git-repo-check", "--ephemeral"} <= set(call["cmd"])
    assert call["cmd"][call["cmd"].index("-m") + 1] == "gpt-5.5"
    assert 'model_reasoning_effort="high"' in call["cmd"]
    assert call["input"] == "long prompt"         # prompt on stdin, not argv
    assert "long prompt" not in call["cmd"]


def test_codex_failure_raises(fake_run):
    fake_run.reply = (1, "", "auth error")
    with pytest.raises(RuntimeError, match="auth error"):
        rb._invoke("p", "codex", "gpt-5.5")


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
