#!/usr/bin/env python3
"""Managed cross-CLI delegation: hand a task to another coding-agent CLI.

Any host CLI (Claude Code, Codex, Antigravity, Copilot) runs this script to
give a task to any target CLI under one set of controls:

- isolation: write tasks run in their own git worktree on ``delegate/<job>``;
  read-only tasks run in place under the target's read-only settings, and any
  change made during the run is reported.
- policy: ``.delegate/policy.json`` limits targets, write access, delegation
  depth, concurrency and timeouts. Flags can only tighten it.
- supervision: every run has a detached supervisor that owns the target's
  process group, enforces the timeout, honours ``cancel`` and records the
  result, so a host whose shell tool times out loses nothing.
- audit: job records, raw output and ``log.jsonl`` live in the git common
  dir (``.git/delegate/``), shared by every worktree of the repository.
- review gate: nothing reaches the caller's branch until ``merge``.

These are guardrails for cooperating agents, not a security boundary: a
delegate with an unrestricted shell can still start another CLI by hand.

Stdlib only, POSIX only, Python 3.9+ (it runs in any configured project).
Run ``delegate.py -h`` or read README.md next to this file.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import ctypes
import fcntl
import functools
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve()
TARGETS = ("claude", "codex", "agy", "copilot")
MODES = ("write", "read-only")
ACTIVE = ("starting", "running")
TERMINAL = ("succeeded", "failed", "timeout", "cancelled", "lost")

(EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_REFUSED, EXIT_RUNNING, EXIT_UNAVAILABLE,
 EXIT_CONFIRM) = range(7)

JOB_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9_-]+)*$")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
START_GRACE_S = 30      # a run with no supervisor pid yet is still starting
KILL_GRACE_S = 10       # SIGTERM → SIGKILL
SUMMARY_CAP = 20_000
# Build artifacts a project forgot to ignore stay out of the auto-commit.
ARTIFACT_EXCLUDES = tuple(f":(exclude,glob)**/{p}" for p in (
    "__pycache__/**", "*.pyc", ".pytest_cache/**", "node_modules/**", ".DS_Store"))
# Linux caps one argv string at 128 KiB; agy and copilot take the prompt as
# an argument, so a longer task is passed as a pointer to its file.
ARGV_PROMPT_CAP = 100_000

DEFAULT_POLICY: dict = {
    "allow_write": True,
    "max_depth": 1,
    "max_concurrent": 3,
    "default_timeout_s": 1800,
    "max_timeout_s": 7200,
    "worktree_root": None,
    "pass_env": [],
    "targets": {
        "claude": {"enabled": True, "model": None, "effort": None},
        # sandbox: "enforce" uses Codex's own sandbox (read-only /
        # workspace-write); "bypass" skips it where it can't start (see
        # `doctor`), leaving the worktree as the only fence — so read-only
        # Codex jobs are refused under "bypass".
        "codex": {"enabled": True, "model": None, "effort": None,
                  "sandbox": "enforce", "network": False},
        "agy": {"enabled": True, "model": None, "effort": None},
        "copilot": {"enabled": True, "model": None, "effort": None},
    },
}
_TARGET_KEYS = {"enabled": (bool,), "model": (str, type(None)), "effort": (str, type(None))}
_CODEX_KEYS = {"sandbox": ("enforce", "bypass"), "network": (bool,)}

# Variables that identify the calling CLI session. A child must not inherit
# them: they would make it misreport its host, and some are credentials for
# the parent's session (Claude Code's messaging token, Antigravity's CSRF
# token).
SESSION_ENV = {
    "CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "AI_AGENT",
    "CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CI", "CODEX_VERSION",
    "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED",
    "COPILOT_CLI", "COPILOT_AGENT_SESSION_ID", "COPILOT_CLI_BINARY_VERSION",
}
SESSION_ENV_PATTERN = re.compile(
    r"^(ANTIGRAVITY_.*|FOUNDRY_DELEGATE_.*"
    r"|CLAUDE_CODE_.*(SESSION|MESSAGING|BRIDGE|SSE_PORT|ENTRYPOINT|EXECPATH|CHILD).*)$")
# Each CLI's own credentials. A child keeps only its target's (plus the
# policy's pass_env), so no key reaches a delegate that has no use for it.
CREDENTIALS = {
    "claude": {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"},
    "codex": {"OPENAI_API_KEY", "CODEX_API_KEY"},
    "agy": {"GEMINI_API_KEY", "GOOGLE_API_KEY"},
    "copilot": {"COPILOT_GITHUB_TOKEN"},
}
HOST_MARKERS = (
    ("codex", ("CODEX_THREAD_ID", "CODEX_SESSION_ID")),
    ("agy", ("ANTIGRAVITY_AGENT", "ANTIGRAVITY_CONVERSATION_ID")),
    ("copilot", ("COPILOT_CLI", "COPILOT_AGENT_SESSION_ID")),
    ("claude", ("CLAUDECODE",)),
)

# Set by the supervisor's signal handlers; checked by its wait loop.
_CANCEL = threading.Event()


class DelegateError(Exception):
    """A failure reported to the caller as JSON with an exit code."""

    def __init__(self, message: str, code: int = EXIT_FAILED, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


# ── small helpers ─────────────────────────────────────────────────────


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def emit(obj: dict) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False), flush=True)


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git(args: list[str], cwd: Path, env: dict | None = None, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, env=env, text=True, capture_output=True)
    if check and proc.returncode != 0:
        detail = (proc.stderr.strip() + "\n" + proc.stdout.strip()).strip()
        raise DelegateError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout.rstrip()  # porcelain lines start with a meaningful space


def git_ok(args: list[str], cwd: Path) -> bool:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True).returncode == 0


def delegate_identity(label: str) -> dict:
    """Author/committer for commits the runner makes. Set through the
    environment: GIT_AUTHOR_* would override `-c user.*`, and this works with
    no git identity configured."""
    return {**os.environ, **{f"GIT_{role}_{field}": value
                             for role in ("AUTHOR", "COMMITTER")
                             for field, value in (("NAME", f"delegate ({label})"),
                                                  ("EMAIL", "delegate@agent-foundry.invalid"))}}


def script_hint() -> str:
    """How to call this script from the current directory (for `next` hints)."""
    try:
        rel = os.path.relpath(SCRIPT, Path.cwd())
    except ValueError:
        rel = str(SCRIPT)
    return f"python3 {rel if not rel.startswith('../..') else SCRIPT}"


@functools.cache
def _valid_branch_name(job: str) -> bool:
    return git_ok(["check-ref-format", f"refs/heads/delegate/{job}"], Path.cwd())


def validate_job_name(job: str) -> str:
    if (not JOB_NAME.match(job) or len(job) > 48 or job.endswith(".lock")
            or not _valid_branch_name(job)):
        raise DelegateError(f"invalid job name {job!r} (use a-z, 0-9, '-', '_' and inner '.')",
                            EXIT_USAGE)
    return job


# ── repository & state layout ─────────────────────────────────────────


class Repo:
    """The caller's checkout, the repository's common git dir (which holds
    the job state for every worktree) and the checkout that holds the policy."""

    def __init__(self, cwd: Path):
        top = git(["rev-parse", "--show-toplevel"], cwd, check=False)
        if not top:
            raise DelegateError(f"not inside a git repository (cwd={cwd})", EXIT_USAGE)
        self.toplevel = Path(top)
        common = Path(git(["rev-parse", "--git-common-dir"], self.toplevel))
        self.common = common if common.is_absolute() else (self.toplevel / common).resolve()
        # The main checkout (when there is one) holds the committed policy;
        # a bare repository's worktrees fall back to their own checkout.
        self.main = self.common.parent if self.common.name == ".git" else None
        self.home = self.main or self.toplevel
        self.name = self.main.name if self.main else self.common.name.removesuffix(".git")
        self.state = self.common / "delegate"
        self.config = self.home / ".delegate"
        self._lock_depth = 0
        self._lock_fh = None

    def ensure_state(self) -> None:
        (self.state / "jobs").mkdir(parents=True, exist_ok=True)

    def job_dir(self, job: str) -> Path:
        return self.state / "jobs" / validate_job_name(job)

    @contextlib.contextmanager
    def lock(self):
        """Exclusive across processes, re-entrant within one."""
        if self._lock_depth == 0:
            self.ensure_state()
            self._lock_fh = (self.state / "lock").open("w")
            fcntl.flock(self._lock_fh, fcntl.LOCK_EX)
        self._lock_depth += 1
        try:
            yield
        finally:
            self._lock_depth -= 1
            if self._lock_depth == 0:
                fcntl.flock(self._lock_fh, fcntl.LOCK_UN)
                self._lock_fh.close()
                self._lock_fh = None

    def log(self, event: str, **fields) -> None:
        self.ensure_state()
        row = {"ts": now_iso(), "event": event, **fields}
        with (self.state / "log.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── policy ────────────────────────────────────────────────────────────


def _type_error(where: str, expected: str) -> DelegateError:
    return DelegateError(f"policy: {where} must be {expected}", EXIT_USAGE)


def _check_scalar(value, allowed: tuple, where: str) -> None:
    if all(isinstance(a, type) for a in allowed):
        # bool is an int in Python; never accept it where a number is meant.
        if (isinstance(value, bool) and bool not in allowed) or not isinstance(value, allowed):
            raise _type_error(where, " or ".join(a.__name__ for a in allowed))
    elif value not in allowed:
        raise _type_error(where, " or ".join(repr(a) for a in allowed))


def _check_names(values, where: str) -> list:
    if not isinstance(values, list) or not all(
            isinstance(v, str) and ENV_NAME.match(v) for v in values):
        raise _type_error(where, "a list of environment variable names")
    return values


def validate_policy(raw: dict) -> None:
    unknown = sorted(set(raw) - set(DEFAULT_POLICY))
    if unknown:
        raise DelegateError(f"policy: unknown keys: {', '.join(unknown)}", EXIT_USAGE)
    for key, kinds in (("allow_write", (bool,)), ("max_depth", (int,)),
                       ("max_concurrent", (int,)), ("default_timeout_s", (int,)),
                       ("max_timeout_s", (int,)), ("worktree_root", (str, type(None)))):
        if key in raw:
            _check_scalar(raw[key], kinds, key)
    for key, low in (("max_depth", 0), ("max_concurrent", 1), ("default_timeout_s", 1),
                     ("max_timeout_s", 1)):
        if key in raw and raw[key] < low:
            raise _type_error(key, f">= {low}")
    if "pass_env" in raw:
        _check_names(raw["pass_env"], "pass_env")
    targets = raw.get("targets", {})
    if not isinstance(targets, dict):
        raise _type_error("targets", "an object")
    for target, cfg in targets.items():
        if target not in TARGETS or not isinstance(cfg, dict):
            raise _type_error(f"targets.{target}", f"an object for one of {', '.join(TARGETS)}")
        schema = {**_TARGET_KEYS, **(_CODEX_KEYS if target == "codex" else {})}
        for key, value in cfg.items():
            if key not in schema:
                raise DelegateError(f"policy: unknown key targets.{target}.{key}", EXIT_USAGE)
            _check_scalar(value, schema[key], f"targets.{target}.{key}")


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        out[key] = _merge(base[key], value) if isinstance(base.get(key), dict) \
            and isinstance(value, dict) else value
    return out


def load_policy(repo: Repo) -> tuple[dict, str]:
    path = repo.config / "policy.json"
    if not path.is_file():
        return _merge(DEFAULT_POLICY, {}), "defaults"
    try:
        raw = read_json(path)
    except (OSError, ValueError) as e:
        raise DelegateError(f"unreadable policy {path}: {e}", EXIT_USAGE) from e
    if not isinstance(raw, dict):
        raise DelegateError(f"policy {path} must be a JSON object", EXIT_USAGE)
    try:
        validate_policy(raw)
    except DelegateError as e:
        raise DelegateError(f"{e} ({path})", EXIT_USAGE) from e
    return _merge(DEFAULT_POLICY, raw), str(path)


# ── environment ───────────────────────────────────────────────────────


def detect_host(env: dict) -> str:
    if env.get("FOUNDRY_DELEGATE_TARGET"):
        return env["FOUNDRY_DELEGATE_TARGET"]
    for host, names in HOST_MARKERS:
        if any(env.get(n) for n in names):
            return host
    return "shell"


def child_env(base: dict, target: str, extra: dict | None = None,
              pass_env: list[str] | None = None) -> dict:
    """Environment for a target CLI: no parent-session variables and no other
    CLI's credentials (unless the policy's pass_env keeps them)."""
    keep = set(pass_env or [])
    drop = set()
    for other, names in CREDENTIALS.items():
        if other != target:
            drop |= names - keep
    env = {k: v for k, v in base.items()
           if k not in SESSION_ENV and not SESSION_ENV_PATTERN.match(k) and k not in drop}
    env.update(extra or {})
    return env


# ── git snapshots ─────────────────────────────────────────────────────


def tree_of_workdir(workdir: Path) -> str:
    """Tree object of the working directory as `git add -A` would stage it.

    Uses a copy of the real index so unchanged files aren't re-hashed.
    """
    index = Path(git(["rev-parse", "--git-path", "index"], workdir))
    index = index if index.is_absolute() else workdir / index
    with tempfile.TemporaryDirectory() as tmp:
        tmp_index = Path(tmp) / "index"
        env = {**os.environ, "GIT_INDEX_FILE": str(tmp_index)}
        if index.is_file():
            shutil.copy2(index, tmp_index)
        else:
            git(["read-tree", "HEAD"], workdir, env)
        git(["add", "-A"], workdir, env)
        return git(["write-tree"], workdir, env)


def refs_snapshot(repo: Repo) -> dict:
    out = git(["for-each-ref", "--format=%(refname) %(objectname)"], repo.toplevel)
    return dict(line.split(" ", 1) for line in out.splitlines() if " " in line)


def ref_changes(before: dict, after: dict, own_branch: str | None) -> list[str]:
    own = f"refs/heads/{own_branch}" if own_branch else None
    changes = []
    for ref in sorted(set(before) | set(after)):
        # Other jobs' branches move on their own while this one runs.
        if ref == own or ref == "refs/stash" or ref.startswith("refs/heads/delegate/"):
            continue
        if ref not in after:
            changes.append(f"deleted {ref}")
        elif ref not in before:
            changes.append(f"created {ref}")
        elif before[ref] != after[ref]:
            changes.append(f"moved {ref}")
    return changes


def branch_tip(repo: Repo, branch: str) -> str | None:
    return git(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], repo.toplevel,
               check=False) or None


def unmerged_commits(repo: Repo, rec: dict) -> int:
    """Commits on the job branch that haven't reached the caller's checkout."""
    tip = branch_tip(repo, rec["branch"]) if rec.get("branch") else None
    if not tip or tip == rec.get("merged_tip"):
        return 0
    if git_ok(["merge-base", "--is-ancestor", tip, "HEAD"], repo.toplevel):
        return 0
    start = rec.get("merged_tip") or rec["base"]
    return int(git(["rev-list", "--count", f"{start}..{tip}"], repo.toplevel) or 0)


def uncommitted_in(workdir: Path) -> list[str]:
    if not workdir.is_dir():
        return []
    out = git(["status", "--porcelain", "--", ".", *ARTIFACT_EXCLUDES], workdir, check=False)
    return out.splitlines()


# ── target CLIs ───────────────────────────────────────────────────────


def compose_prompt(task: str, ctx: dict) -> str:
    who = f"{ctx['host']} → {ctx['target']}, job {ctx['job']}"
    lines = [
        f"You are a delegated coding agent started non-interactively by agent-foundry "
        f"`delegate` ({who}). No human is watching this run: do not ask questions or wait "
        "for confirmation — make reasonable decisions, note them, and finish the task.",
    ]
    if ctx["mode"] == "write":
        lines.append(
            f"Work only inside {ctx['workdir']}, a git worktree on branch {ctx['branch']}. "
            "Do not push, switch branches, rewrite history, or touch files outside it. "
            "You don't need to commit: anything left uncommitted is committed for you "
            "on this branch when you finish.")
    else:
        tools = ("Shell commands are disabled for this run: an attempt fails, and on "
                 "some CLIs ends the run with no answer. Use your file-reading and search "
                 "tools only." if ctx["cli"] in ("agy", "copilot") else
                 "Read files and run read-only commands if your tools allow them.")
        lines.append("This is a read-only task: do not create, modify or delete any files. "
                     f"{tools} Then report.")
    if not ctx["may_delegate"]:
        lines.append("Do not hand this task, or any part of it, to another agent CLI.")
    lines.append("Finish with a short report: what you did, how you verified it, and "
                 "anything left undone or uncertain.")
    return "\n\n".join([*lines, "---", "Task:", task.strip()]) + "\n"


def argv_prompt(prompt: str, prompt_file: Path) -> tuple[str, bool]:
    """Prompt text for an argv-only CLI; a pointer if it's too long."""
    if len(prompt.encode("utf-8")) <= ARGV_PROMPT_CAP:
        return prompt, False
    return (f"Your full task is in the file {prompt_file}. Read that whole file first, "
            "then do exactly what it says."), True


def build_command(spec: dict, prompt: str, run_dir: Path) -> dict:
    """argv/stdin for one run of the target CLI.

    spec: target, mode, model, effort, resume (session id or None),
    workdir, codex_sandbox, codex_network.
    """
    target, write = spec["target"], spec["mode"] == "write"
    model, effort, resume = spec.get("model"), spec.get("effort"), spec.get("resume")
    final_file = run_dir / "final.txt"
    prompt_file = run_dir / "prompt.md"
    stdin: str | None = None

    if target == "claude":
        argv = ["claude", "-p", "--output-format", "json", "--permission-prompts", "none"]
        if write:
            argv += ["--dangerously-skip-permissions", "--disallowedTools", "Bash(git push:*)"]
        else:
            argv += ["--permission-mode", "dontAsk",
                     "--disallowedTools", "Edit,Write,NotebookEdit,Bash(git push:*)"]
        argv += ["--model", model] if model else []
        argv += ["--effort", effort] if effort else []
        argv += ["--resume", resume] if resume else []
        stdin = prompt
    elif target == "codex":
        argv = ["codex", "exec"] + (["resume"] if resume else [])
        argv += ["--json", "-o", str(final_file), "--skip-git-repo-check",
                 "-c", 'approval_policy="never"']
        if spec.get("codex_sandbox") == "bypass":
            argv += ["--dangerously-bypass-approvals-and-sandbox"]
        else:
            argv += ["-c", f'sandbox_mode="{"workspace-write" if write else "read-only"}"']
            if write and spec.get("codex_network"):
                argv += ["-c", "sandbox_workspace_write.network_access=true"]
        argv += ["-m", model] if model else []
        argv += ["-c", f'model_reasoning_effort="{effort}"'] if effort else []
        argv += [resume, "-"] if resume else []
        stdin = prompt
    elif target == "agy":
        text, pointer = argv_prompt(prompt, prompt_file)
        # agy works in a scratch directory unless the workspace is added.
        argv = ["agy", "-p", text, "--output-format", "json", "--add-dir", spec["workdir"]]
        argv += ["--add-dir", str(run_dir)] if pointer else []
        argv += ["--dangerously-skip-permissions"] if write else []
        argv += ["--model", model] if model else []
        argv += ["--effort", effort] if effort else []
        argv += ["--conversation", resume] if resume else []
    elif target == "copilot":
        text, pointer = argv_prompt(prompt, prompt_file)
        argv = ["copilot", "-p", text, "--output-format", "json", "--no-color",
                "--no-ask-user", "--no-auto-update", "--allow-all-tools"]
        if write:
            argv += ["--deny-tool", "shell(git push)"]
        else:
            # Deny rules beat allow rules, so read-only means no shell at all.
            argv += ["--deny-tool", "write", "--deny-tool", "shell"]
        argv += ["--add-dir", str(run_dir)] if pointer else []
        argv += ["--model", model] if model else []
        argv += ["--effort", effort] if effort else []
        argv += [f"--resume={resume}"] if resume else []
    else:
        raise DelegateError(f"unknown target: {target}", EXIT_USAGE)
    return {"argv": argv, "stdin": stdin, "final_file": final_file}


def _json_lines(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            with contextlib.suppress(ValueError):
                rows.append(json.loads(line))
    return rows


def _last_json_object(text: str) -> dict | None:
    rows = _json_lines(text)
    if rows:
        return rows[-1]
    with contextlib.suppress(ValueError):
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    return None


def _literal(value):
    """agy reports some fields as Python-literal strings ("{'a': 1}")."""
    if isinstance(value, str) and value[:1] in "{[":
        with contextlib.suppress(ValueError, SyntaxError):
            return ast.literal_eval(value)
    return value


def parse_output(target: str, stdout: str, stderr: str, final_file: Path) -> dict:
    """Normalize a target's output: summary, session_id, usage, error, model."""
    res: dict = {"summary": "", "session_id": None, "usage": {}, "error": None,
                 "model_used": None}
    if target == "claude":
        obj = _last_json_object(stdout) or {}
        res["summary"] = obj.get("result") or ""
        res["session_id"] = obj.get("session_id")
        res["model_used"] = ", ".join(obj.get("modelUsage") or {}) or None
        res["usage"] = {k: obj[k] for k in ("total_cost_usd", "num_turns", "duration_ms")
                        if k in obj}
        if obj.get("permission_denials"):
            res["usage"]["permission_denials"] = len(obj["permission_denials"])
        if obj.get("is_error") or not obj:
            res["error"] = obj.get("result") or stderr.strip()[-2000:] or "no JSON result"
    elif target == "codex":
        if final_file.is_file():
            res["summary"] = final_file.read_text(encoding="utf-8", errors="replace").strip()
        for ev in _json_lines(stdout):
            kind = ev.get("type")
            if kind == "thread.started":
                res["session_id"] = ev.get("thread_id")
            elif kind == "turn.completed":
                res["usage"] = ev.get("usage") or {}
            elif kind in ("turn.failed", "error"):
                err = ev.get("error") or ev
                res["error"] = err.get("message") if isinstance(err, dict) else str(err)
    elif target == "agy":
        obj = _last_json_object(stdout) or {}
        res["summary"] = (obj.get("response") or "").strip()
        res["session_id"] = obj.get("conversation_id")
        res["usage"] = _literal(obj.get("usage")) or {}
        denied = _literal(obj.get("denied_actions"))
        if denied:
            res["usage"]["denied_actions"] = denied
        if obj.get("error") or (obj.get("status") not in (None, "SUCCESS")):
            res["error"] = str(obj.get("error") or obj.get("status"))
        elif not res["summary"]:
            # agy exits 0 with an empty response when a tool was denied.
            res["error"] = stderr.strip()[-2000:] or "empty response"
    elif target == "copilot":
        events = _json_lines(stdout)
        replies = [e["data"] for e in events
                   if e.get("type") == "assistant.message" and isinstance(e.get("data"), dict)]
        messages = [r.get("content", "") for r in replies]
        res["model_used"] = next((r["model"] for r in reversed(replies) if r.get("model")), None)
        res["summary"] = next((m for m in reversed(messages) if m.strip()), "").strip()
        result = next((e for e in reversed(events) if e.get("type") == "result"), None)
        if result:
            res["session_id"] = result.get("sessionId")
            res["usage"] = result.get("usage") or {}
            if result.get("exitCode"):
                res["error"] = f"copilot exit code {result['exitCode']}"
        elif not events:
            res["summary"] = stdout.strip()
    return res


def cli_version(target: str) -> str | None:
    if not shutil.which(target):
        return None
    try:
        proc = subprocess.run([target, "--version"], capture_output=True, text=True,
                              timeout=20, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (proc.stdout or proc.stderr).strip().splitlines()
    return out[0] if proc.returncode == 0 and out else None


def codex_sandbox_works() -> bool:
    try:
        proc = subprocess.run(["codex", "sandbox", "--", "true"], capture_output=True,
                              timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


# ── processes ─────────────────────────────────────────────────────────


def _parent_death_signal():
    """preexec_fn making the target die with its supervisor (Linux prctl
    PR_SET_PDEATHSIG). Resolved before fork; None where unavailable."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        prctl = ctypes.CDLL(None, use_errno=True).prctl
    except (OSError, AttributeError):
        return None
    return lambda: prctl(1, int(signal.SIGKILL), 0, 0, 0)


def _cmdline(pid: int) -> str:
    proc = Path(f"/proc/{pid}/cmdline")
    if proc.exists():
        with contextlib.suppress(OSError):
            return proc.read_bytes().replace(b"\0", b" ").decode(errors="replace")
        return ""
    out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True,
                         text=True)
    return out.stdout.strip()


def supervisor_alive(pid: int | None, job: str) -> bool:
    """Is this pid still our supervisor for this job (not a reused pid)?"""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False  # not ours: the pid was reused by another user's process
    cmd = _cmdline(pid)
    return not cmd or ("_supervise" in cmd and job in cmd)


def group_members(pgid: int) -> list[int]:
    """Live processes in a process group (Linux /proc; elsewhere via ps)."""
    if Path("/proc/self/stat").exists():
        members = []
        for stat in Path("/proc").glob("[0-9]*/stat"):
            with contextlib.suppress(OSError, ValueError, IndexError):
                fields = stat.read_text().rsplit(")", 1)[1].split()
                if int(fields[2]) == pgid and fields[0] != "Z":
                    members.append(int(stat.parent.name))
        return members
    out = subprocess.run(["ps", "-A", "-o", "pid=,pgid="], capture_output=True, text=True)
    return [int(p) for p, g in (line.split() for line in out.stdout.splitlines()
                                if len(line.split()) == 2) if int(g) == pgid]


def kill_orphans(pgid: int | None, workdir: str) -> bool:
    """Kill what's left of a target's process group after its supervisor
    died, but only if a member still works in the job's directory (the pgid
    could have been reused)."""
    if not pgid:
        return False
    members = group_members(pgid)
    ours = False
    for pid in members:
        with contextlib.suppress(OSError):
            cwd = str(Path(f"/proc/{pid}/cwd").readlink())
            ours = ours or cwd == workdir or cwd.startswith(workdir.rstrip("/") + "/")
    if not members or (Path("/proc/self/cwd").exists() and not ours):
        return False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, sig)
        time.sleep(1 if sig == signal.SIGTERM else 0)
    return True


# ── jobs ──────────────────────────────────────────────────────────────


def job_exists(repo: Repo, job: str) -> bool:
    return (repo.job_dir(job) / "job.json").is_file()


def load_job(repo: Repo, job: str) -> dict:
    path = repo.job_dir(job) / "job.json"
    if not path.is_file():
        raise DelegateError(f"no such job: {job}", EXIT_USAGE)
    return read_json(path)


def save_job(repo: Repo, rec: dict) -> None:
    write_json(repo.job_dir(rec["job"]) / "job.json", rec)


def update_job(repo: Repo, job: str, **fields) -> dict:
    with repo.lock():
        rec = load_job(repo, job)
        rec.update(fields)
        save_job(repo, rec)
    return rec


def update_run(repo: Repo, job: str, n: int, **fields) -> dict:
    """Change one run's fields under the lock, leaving other runs alone."""
    with repo.lock():
        rec = load_job(repo, job)
        rec["runs"][n - 1].update(fields)
        save_job(repo, rec)
    return rec


def run_dir(repo: Repo, job: str, n: int) -> Path:
    return repo.job_dir(job) / str(n)


def last_run(rec: dict) -> dict | None:
    return rec["runs"][-1] if rec.get("runs") else None


def job_status(rec: dict) -> str:
    run = last_run(rec)
    return run["status"] if run else "idle"


def refresh_status(repo: Repo, rec: dict) -> dict:
    """Mark a run whose supervisor is gone as lost, and stop what it left."""
    run = last_run(rec)
    if not run or run["status"] not in ACTIVE:
        return rec
    pid = run.get("supervisor_pid")
    if pid:
        alive = supervisor_alive(pid, rec["job"])
    else:
        alive = time.time() - run.get("started_ts", 0) < START_GRACE_S
    if alive:
        return rec
    killed = kill_orphans(run.get("child_pgid"), rec["workdir"])
    note = "its supervisor stopped without recording a result"
    if killed:
        note += "; the target CLI it left running was stopped"
    return update_run(repo, rec["job"], run["run"], status="lost", finished=now_iso(),
                      warnings=[*run.get("warnings", []), note])


def all_jobs(repo: Repo) -> list[dict]:
    jobs = repo.state / "jobs"
    recs = []
    for path in sorted(jobs.glob("*/job.json")) if jobs.is_dir() else []:
        with contextlib.suppress(OSError, ValueError, KeyError, DelegateError):
            recs.append(refresh_status(repo, read_json(path)))
    return recs


def running_count(repo: Repo) -> int:
    return sum(job_status(rec) in ACTIVE for rec in all_jobs(repo))


def effective_depth(repo: Repo) -> int:
    """Delegation depth of the caller: its environment marker, or — if a CLI
    filtered the environment — the depth of the running job whose worktree
    the caller is in."""
    depth = int(os.environ.get("FOUNDRY_DELEGATE_DEPTH", "0") or 0)
    here = repo.toplevel.resolve()
    for rec in all_jobs(repo):
        run = last_run(rec)
        if (rec["mode"] == "write" and run and run["status"] in ACTIVE
                and Path(rec["workdir"]).resolve() == here):
            depth = max(depth, run.get("depth", 1))
    return depth


def worktree_path(repo: Repo, policy: dict, job: str) -> Path:
    root = policy.get("worktree_root")
    base = (repo.home / Path(root).expanduser()).resolve() if root else repo.home.parent
    return base / f"{repo.name}-delegate-{job}"


def create_worktree(repo: Repo, rec: dict, include_dirty: bool, base_ref: str | None) -> None:
    """Create the job's worktree and branch at the chosen base."""
    top = repo.toplevel
    base = git(["rev-parse", "--verify", f"{base_ref or 'HEAD'}^{{commit}}"], top)
    dirty = git(["status", "--porcelain"], top)
    rec["snapshot"] = False
    if include_dirty and dirty and not base_ref:
        tree = tree_of_workdir(top)
        if tree != git(["rev-parse", "HEAD^{tree}"], top):
            base = git(["commit-tree", "--no-gpg-sign", tree, "-p", base, "-m",
                        f"delegate: snapshot of uncommitted work for job {rec['job']}"],
                       top, env=delegate_identity("snapshot"))
            rec["snapshot"] = True
    elif dirty and not base_ref:
        rec["base_note"] = (f"{len(dirty.splitlines())} uncommitted change(s) in "
                            f"{top} were not visible to the delegate (use --include-dirty)")
    rec["base"] = base
    git(["worktree", "add", "-b", rec["branch"], rec["workdir"], base], top)


def remove_worktree(repo: Repo, rec: dict) -> None:
    if Path(rec["workdir"]).exists():
        git(["worktree", "remove", "--force", rec["workdir"]], repo.toplevel, check=False)
    git(["worktree", "prune"], repo.toplevel, check=False)
    if branch_tip(repo, rec["branch"]):
        git(["branch", "-D", rec["branch"]], repo.toplevel, check=False)


def new_job(repo: Repo, policy: dict, job: str | None, mode: str, target: str) -> dict:
    job = validate_job_name(
        job or f"{target}-{time.strftime('%m%d-%H%M')}-{os.urandom(2).hex()}")
    rec = {"job": job, "target": target, "mode": mode,
           "created": now_iso(), "runs": []}
    if mode == "write":
        rec["branch"] = f"delegate/{job}"
        rec["workdir"] = str(worktree_path(repo, policy, job))
        if Path(rec["workdir"]).exists():
            raise DelegateError(f"{rec['workdir']} already exists — pick another --job",
                                EXIT_USAGE)
        if branch_tip(repo, rec["branch"]):
            raise DelegateError(f"branch {rec['branch']} already exists — pick another --job",
                                EXIT_USAGE)
    else:
        rec["workdir"] = str(repo.toplevel)
    return rec


def register_job(repo: Repo, rec: dict, include_dirty: bool, base_ref: str | None) -> None:
    """Create the job's record (and worktree); leave nothing behind on failure."""
    repo.job_dir(rec["job"]).mkdir(parents=True)
    try:
        if rec["mode"] == "write":
            create_worktree(repo, rec, include_dirty, base_ref)
        save_job(repo, rec)
    except BaseException:
        if rec["mode"] == "write":
            remove_worktree(repo, rec)
        shutil.rmtree(repo.job_dir(rec["job"]), ignore_errors=True)
        raise


def read_task(args) -> str:
    if args.task_file:
        text = (sys.stdin.read() if args.task_file == "-"
                else Path(args.task_file).read_text(encoding="utf-8"))
    else:
        text = args.task or ""
    if not text.strip():
        raise DelegateError("the task is empty (--task TEXT or --task-file PATH|-)", EXIT_USAGE)
    return text


def check_target(name: str) -> str:
    if name not in TARGETS:
        raise DelegateError(f"unknown target {name!r} — choose one of {', '.join(TARGETS)}",
                            EXIT_USAGE)
    return name


def check_policy(repo: Repo, policy: dict, target: str, mode: str,
                 timeout: int | None) -> int:
    """Refuse what the policy forbids; return the effective timeout."""
    cfg = policy["targets"][target]
    if not cfg.get("enabled"):
        raise DelegateError(f"target {target} is disabled by policy", EXIT_REFUSED)
    if mode == "write" and not policy["allow_write"]:
        raise DelegateError("write delegation is disabled by policy (allow_write=false)",
                            EXIT_REFUSED)
    if target == "codex" and mode == "read-only" and cfg.get("sandbox") == "bypass":
        raise DelegateError(
            "read-only Codex needs Codex's sandbox, and the policy bypasses it "
            "(targets.codex.sandbox=\"bypass\"): nothing would stop it writing in your "
            "checkout. Use write mode (its own worktree) and discard the job afterwards.",
            EXIT_REFUSED)
    depth = effective_depth(repo)
    if depth >= policy["max_depth"]:
        raise DelegateError(
            f"delegation depth limit reached (depth {depth}, max_depth "
            f"{policy['max_depth']}): a delegate may not delegate further", EXIT_REFUSED)
    if os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1":
        raise DelegateError(
            "running inside Codex's sandbox: the target CLI needs network access and its "
            "own config directory, and a sandboxed background job dies with the command. "
            "Re-run this command with escalated permissions (outside the sandbox).",
            EXIT_REFUSED)
    effective = timeout or policy["default_timeout_s"]
    if effective <= 0 or effective > policy["max_timeout_s"]:
        raise DelegateError(f"--timeout {effective}s must be between 1 and the policy's "
                            f"max_timeout_s ({policy['max_timeout_s']})", EXIT_REFUSED)
    return effective


def _check_follow_up(rec: dict, args) -> None:
    if job_status(rec) in ACTIVE:
        raise DelegateError(f"job {rec['job']} is still running", EXIT_RUNNING)
    if args.to and check_target(args.to) != rec["target"]:
        raise DelegateError(f"job {rec['job']} belongs to {rec['target']}", EXIT_USAGE)
    if args.mode and args.mode != rec["mode"]:
        raise DelegateError(f"job {rec['job']} is a {rec['mode']} job", EXIT_USAGE)


def prepare_run(repo: Repo, args) -> tuple[dict, int]:
    """Validate, register a run (and its job and worktree); return (job, run#)."""
    policy, _ = load_policy(repo)
    task = read_task(args)
    with repo.lock():
        rec = load_job(repo, args.job) if args.job and job_exists(repo, args.job) else None
        if rec:
            rec = refresh_status(repo, rec)
            _check_follow_up(rec, args)
            target, mode = rec["target"], rec["mode"]
        else:
            if not args.to:
                raise DelegateError("--to is required for a new job", EXIT_USAGE)
            if args.resume:
                raise DelegateError("--resume needs an existing --job", EXIT_USAGE)
            target = check_target(args.to)
            mode = args.mode or "write"
        timeout = check_policy(repo, policy, target, mode, args.timeout)
        if not shutil.which(target):
            raise DelegateError(f"{target} CLI is not installed (not on PATH)",
                                EXIT_UNAVAILABLE)
        if running_count(repo) >= policy["max_concurrent"]:
            raise DelegateError(f"max_concurrent={policy['max_concurrent']} jobs already "
                                "running — wait for one to finish", EXIT_REFUSED)
        if rec is None:
            rec = new_job(repo, policy, args.job, mode, target)
            register_job(repo, rec, args.include_dirty, args.base)
        n = register_run(repo, rec, args, policy, task, timeout)
    return load_job(repo, rec["job"]), n


def register_run(repo: Repo, rec: dict, args, policy: dict, task: str, timeout: int) -> int:
    target_cfg = policy["targets"][rec["target"]]
    model = args.model or target_cfg.get("model")
    resume = None
    if args.resume:
        resume = next((r.get("session_id") for r in reversed(rec["runs"])
                       if r.get("session_id")), None)
        if not resume:
            raise DelegateError(f"job {rec['job']} has no session to resume", EXIT_USAGE)
    depth = effective_depth(repo)
    host = detect_host(dict(os.environ))
    chain = os.environ.get("FOUNDRY_DELEGATE_CHAIN") or host
    n = len(rec["runs"]) + 1
    rdir = run_dir(repo, rec["job"], n)
    shutil.rmtree(rdir, ignore_errors=True)  # debris of an unregistered attempt
    rdir.mkdir(parents=True)
    label = rec["target"]
    ctx = {"host": host, "target": label, "cli": label, "job": rec["job"],
           "mode": rec["mode"], "workdir": rec["workdir"], "branch": rec.get("branch"),
           "may_delegate": depth + 1 < policy["max_depth"]}
    (rdir / "prompt.md").write_text(compose_prompt(task, ctx), encoding="utf-8")
    rec["runs"].append({
        "run": n, "status": "starting", "started": now_iso(), "started_ts": time.time(),
        "host": host, "depth": depth + 1, "chain": f"{chain}>{label}", "model": model,
        "effort": args.effort or target_cfg.get("effort"), "timeout_s": timeout,
        "resume": resume, "task_sha256": hashlib.sha256(task.encode()).hexdigest()[:16],
        "codex_sandbox": target_cfg.get("sandbox"), "codex_network": target_cfg.get("network"),
        "pass_env": list(policy.get("pass_env", [])),
    })
    save_job(repo, rec)
    repo.log("start", job=rec["job"], run=n, host=host, target=rec["target"],
             mode=rec["mode"], model=model, depth=depth + 1,
             chain=rec["runs"][-1]["chain"], timeout_s=timeout,
             task=task.strip().splitlines()[0][:80])
    return n


# ── supervising a run ─────────────────────────────────────────────────


class Supervisor:
    """Runs the target CLI for one run in its own process group, enforcing
    the timeout and cancellation, and always records a final status."""

    def __init__(self, repo: Repo, job: str, n: int):
        self.repo, self.job, self.n = repo, job, n
        self.rec = load_job(repo, job)
        self.run = self.rec["runs"][n - 1]
        self.dir = run_dir(repo, job, n)
        self.workdir = Path(self.rec["workdir"])
        self.proc: subprocess.Popen | None = None
        self.pgid: int | None = None

    def cancel_requested(self) -> bool:
        return _CANCEL.is_set() or (self.dir / "cancel").exists()

    def _env(self) -> dict:
        return child_env(dict(os.environ), self.rec["target"], {
            "FOUNDRY_DELEGATE_DEPTH": str(self.run["depth"]),
            "FOUNDRY_DELEGATE_CHAIN": self.run["chain"],
            "FOUNDRY_DELEGATE_TARGET": self.rec["target"],
            "FOUNDRY_DELEGATE_JOB": self.job,
        }, self.run.get("pass_env"))

    def execute(self) -> dict:
        update_run(self.repo, self.job, self.n, status="running", supervisor_pid=os.getpid())
        start = time.monotonic()
        status, code, parsed, before = "failed", None, {}, {}
        try:
            before = self._snapshot()
            env = self._env()
            cmd = build_command({**self.run, "target": self.rec["target"],
                                 "mode": self.rec["mode"], "workdir": str(self.workdir)},
                                (self.dir / "prompt.md").read_text(encoding="utf-8"), self.dir)
            if self.cancel_requested():
                status = "cancelled"
            else:
                status, code = self._run_child(cmd, env, start + self.run["timeout_s"])
                parsed = parse_output(self.rec["target"], self._read("stdout.log"),
                                      self._read("stderr.log"), cmd["final_file"])
                if status == "exited":
                    status = "succeeded" if code == 0 and not parsed["error"] else "failed"
        except DelegateError as e:
            parsed = {**parsed, "error": str(e)}
        except Exception as e:  # never leave a run recorded as running
            parsed = {**parsed, "error": f"supervisor error: {e!r}"}
        finally:
            self._sweep()
        return self._finish(status, code, time.monotonic() - start, parsed, before)

    def _run_child(self, cmd: dict, env: dict, deadline: float) -> tuple[str, int | None]:
        with (self.dir / "stdout.log").open("wb") as out, \
                (self.dir / "stderr.log").open("wb") as err:
            try:
                self.proc = subprocess.Popen(
                    cmd["argv"], cwd=self.workdir, env=env, stdout=out, stderr=err,
                    stdin=subprocess.PIPE if cmd["stdin"] is not None else subprocess.DEVNULL,
                    start_new_session=True, preexec_fn=_parent_death_signal())
            except OSError as e:
                raise DelegateError(f"could not start {cmd['argv'][0]}: {e}") from e
            self.pgid = self.proc.pid
            update_run(self.repo, self.job, self.n, child_pgid=self.pgid)
            if cmd["stdin"] is not None:
                threading.Thread(target=self._feed, args=(cmd["stdin"],), daemon=True).start()
            reason, kill_at = "exited", None
            while self.proc.poll() is None:
                now = time.monotonic()
                if reason == "exited" and (self.cancel_requested() or now > deadline):
                    reason = "cancelled" if self.cancel_requested() else "timeout"
                    self._signal(signal.SIGTERM)
                    kill_at = now + KILL_GRACE_S
                elif kill_at and now > kill_at:
                    self._signal(signal.SIGKILL)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    self.proc.wait(timeout=1)
        return reason, self.proc.returncode

    def _feed(self, text: str) -> None:
        with contextlib.suppress(BrokenPipeError, OSError):
            self.proc.stdin.write(text.encode("utf-8"))
            self.proc.stdin.close()

    def _signal(self, sig: int) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(self.pgid, sig)

    def _sweep(self) -> None:
        """Stop anything the target left running in its process group."""
        if not self.pgid:
            return
        if self.proc and self.proc.poll() is None:
            self._signal(signal.SIGKILL)
            self.proc.wait()
        if group_members(self.pgid):
            self._signal(signal.SIGTERM)
            end = time.monotonic() + 2
            while group_members(self.pgid) and time.monotonic() < end:
                time.sleep(0.1)
            self._signal(signal.SIGKILL)

    def _read(self, name: str) -> str:
        path = self.dir / name
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

    def _snapshot(self) -> dict:
        snap: dict = {"refs": refs_snapshot(self.repo)}
        if self.rec["mode"] == "read-only":
            snap["tree"] = tree_of_workdir(self.workdir)
        else:
            snap["tip"] = branch_tip(self.repo, self.rec["branch"])
        return snap

    def _finish(self, status: str, code: int | None, elapsed: float, parsed: dict,
                before: dict) -> dict:
        summary = parsed.get("summary") or ""
        with contextlib.suppress(OSError):
            (self.dir / "summary.md").write_text(summary + "\n", encoding="utf-8")
        warnings: list[str] = []
        changes: list[str] = []
        commits = 0
        try:
            if self.rec["mode"] == "write" and before.get("tip"):
                changes, commits, extra = self._collect_write(before["tip"])
                warnings += extra
            elif before.get("tree"):
                after = tree_of_workdir(self.workdir)
                if after != before["tree"]:
                    changes = git(["diff-tree", "-r", "--name-only", before["tree"], after],
                                  self.workdir).splitlines()
                    warnings.append(f"{len(changes)} file(s) changed in {self.workdir} during "
                                    "this read-only run (by the delegate, or by you meanwhile)")
            if "refs" in before:
                moved = ref_changes(before["refs"], refs_snapshot(self.repo),
                                    self.rec.get("branch"))
                if moved:
                    warnings.append("refs changed during the run (by you or the delegate): "
                                    + ", ".join(moved))
        except Exception as e:  # report, but still record the run
            warnings.append(f"could not inspect the result: {e}")
        update_run(self.repo, self.job, self.n,
                   status=status, finished=now_iso(), exit_code=code,
                   model_used=parsed.get("model_used"), duration_s=round(elapsed, 1),
                   session_id=parsed.get("session_id"), usage=parsed.get("usage") or {},
                   error=parsed.get("error"), files_changed=changes, commits=commits,
                   warnings=warnings)
        self.repo.log("end", job=self.job, run=self.n, target=self.rec["target"],
                      status=status, exit_code=code, duration_s=round(elapsed, 1),
                      files_changed=len(changes), warnings=len(warnings))
        return result_view(self.repo, load_job(self.repo, self.job), self.n)

    def _collect_write(self, tip_before: str) -> tuple[list[str], int, list[str]]:
        warnings = []
        branch = self.rec["branch"]
        head = git(["symbolic-ref", "-q", "HEAD"], self.workdir, check=False)
        if head != f"refs/heads/{branch}":
            warnings.append(f"the delegate left {self.workdir} on "
                            f"{head or 'a detached HEAD'} instead of {branch}; nothing was "
                            "auto-committed")
        elif git(["status", "--porcelain"], self.workdir):
            git(["add", "-A", "--", ".", *ARTIFACT_EXCLUDES], self.workdir)
            if not git_ok(["diff", "--cached", "--quiet"], self.workdir):
                label = self.rec["target"]
                git(["commit", "-q", "--no-verify", "--no-gpg-sign", "-m",
                     f"delegate[{self.job}#{self.n}]: uncommitted work from {label}"],
                    self.workdir, env=delegate_identity(label))
            status = git(["status", "--porcelain", "--untracked-files=all"], self.workdir)
            leftover = [line for line in status.splitlines() if line[:1] in "? "]
            if leftover:
                warnings.append(f"left {len(leftover)} build artifact(s) uncommitted in "
                                "the worktree")
        tip = branch_tip(self.repo, branch)
        if not tip:
            return [], 0, [*warnings, f"branch {branch} no longer exists"]
        changes = git(["diff", "--name-only", f"{tip_before}..{tip}"],
                      self.repo.toplevel).splitlines()
        commits = int(git(["rev-list", "--count", f"{tip_before}..{tip}"],
                          self.repo.toplevel) or 0)
        return changes, commits, warnings


def result_view(repo: Repo, rec: dict, n: int | None = None) -> dict:
    base = {"job": rec["job"], "target": rec["target"], "mode": rec["mode"], "workdir": rec["workdir"], "branch": rec.get("branch")}
    run = rec["runs"][(n or len(rec["runs"])) - 1] if rec["runs"] else None
    if not run:
        return {**base, "run": 0, "status": "idle", "next": next_steps(repo, rec, None)}
    rdir = run_dir(repo, rec["job"], run["run"])
    summary_path = rdir / "summary.md"
    summary = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
    view = {
        **base, "run": run["run"], "status": run["status"],
        "model": run.get("model") or run.get("model_used"),
        "host": run.get("host"), "chain": run.get("chain"),
        "exit_code": run.get("exit_code"), "duration_s": run.get("duration_s"),
        "files_changed": run.get("files_changed", []), "commits": run.get("commits", 0),
        "session_id": run.get("session_id"), "usage": run.get("usage", {}),
        "error": run.get("error"), "warnings": run.get("warnings", []),
        "summary": summary[:SUMMARY_CAP],
        "summary_file": str(summary_path), "output_dir": str(rdir),
    }
    if len(summary) > SUMMARY_CAP:
        view["summary_truncated"] = True
    if rec.get("base_note"):
        view["base_note"] = rec["base_note"]
    view["next"] = next_steps(repo, rec, run)
    return view


def next_steps(repo: Repo, rec: dict, run: dict | None) -> list[str]:
    s, job = script_hint(), rec["job"]
    if run and run["status"] in ACTIVE:
        return [f"{s} wait {job}", f"{s} log {job}", f"{s} cancel {job}"]
    steps = []
    if rec["mode"] == "write":
        with contextlib.suppress(DelegateError):
            if unmerged_commits(repo, rec):
                steps += [f"{s} diff {job}", f"{s} merge {job}   # after the user approves"]
        steps.append(f"{s} discard {job}   # after the user approves")
    steps.append(f"{s} run --job {job} --resume --task '...'   # follow up in the same session")
    return steps


def exit_code_for(status: str) -> int:
    return {"succeeded": EXIT_OK, "idle": EXIT_OK, "starting": EXIT_RUNNING,
            "running": EXIT_RUNNING}.get(status, EXIT_FAILED)


# ── subcommands ───────────────────────────────────────────────────────


def spawn_supervisor(repo: Repo, rec: dict, n: int) -> None:
    rdir = run_dir(repo, rec["job"], n)
    with (rdir / "supervisor.log").open("wb") as log:
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT), "_supervise", rec["job"], str(n)],
            cwd=repo.toplevel, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True)
    update_run(repo, rec["job"], n, supervisor_pid=proc.pid)


def wait_for(repo: Repo, job: str, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while True:
        rec = refresh_status(repo, load_job(repo, job))
        status = job_status(rec)
        if status not in ACTIVE or time.monotonic() >= deadline:
            view = result_view(repo, rec)
            if status in ACTIVE:
                view["note"] = (f"still running after waiting {int(timeout)}s — it keeps "
                                "going in the background; call wait again")
            emit(view)
            return exit_code_for(status)
        time.sleep(1)


def cmd_run(repo: Repo, args) -> int:
    """start + a bounded wait: a host whose shell tool times out loses nothing."""
    rec, n = prepare_run(repo, args)
    spawn_supervisor(repo, rec, n)
    return wait_for(repo, rec["job"], args.wait)


def cmd_start(repo: Repo, args) -> int:
    rec, n = prepare_run(repo, args)
    spawn_supervisor(repo, rec, n)
    rec = load_job(repo, rec["job"])
    emit({"job": rec["job"], "run": n, "status": "running", "target": rec["target"],
          "mode": rec["mode"], "workdir": rec["workdir"],
          "branch": rec.get("branch"), "next": next_steps(repo, rec, last_run(rec))})
    return EXIT_OK


def cmd_supervise(repo: Repo, args) -> int:
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: _CANCEL.set())
    view = Supervisor(repo, args.job, args.run).execute()
    return exit_code_for(view["status"])


def cmd_wait(repo: Repo, args) -> int:
    return wait_for(repo, args.job, args.timeout)


def cmd_status(repo: Repo, args) -> int:
    rec = refresh_status(repo, load_job(repo, args.job))
    view = result_view(repo, rec, args.run)
    emit(view)
    return exit_code_for(view["status"])


def cmd_list(repo: Repo, args) -> int:
    rows = []
    for rec in all_jobs(repo):
        run = last_run(rec)
        rows.append({"job": rec["job"], "target": rec["target"],
                     "mode": rec["mode"], "runs": len(rec["runs"]), "status": job_status(rec),
                     "started": run["started"] if run else rec["created"],
                     "files_changed": len(run.get("files_changed", [])) if run else 0})
    rows.sort(key=lambda r: r["started"])
    if args.json:
        emit({"jobs": rows})
    elif not rows:
        print("no delegate jobs")
    else:
        print(f"{'JOB':28} {'TARGET':9} {'MODE':9} {'STATUS':10} {'FILES':>5}  STARTED")
        for r in rows:
            print(f"{r['job']:28} {r['target']:9} {r['mode']:9} {r['status']:10} "
                  f"{r['files_changed']:>5}  {r['started']}")
    return EXIT_OK


def cmd_log(repo: Repo, args) -> int:
    rec = load_job(repo, args.job)
    if not rec["runs"]:
        print(f"job {args.job} has no runs")
        return EXIT_OK
    rdir = run_dir(repo, rec["job"], args.run or len(rec["runs"]))
    for name in ("stdout.log", "stderr.log", "supervisor.log"):
        path = rdir / name
        if path.exists() and path.stat().st_size:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            print(f"── {name} (last {min(args.lines, len(lines))} of {len(lines)} lines) ──")
            print("\n".join(lines[-args.lines:]))
    return EXIT_OK


def cmd_cancel(repo: Repo, args) -> int:
    rec = refresh_status(repo, load_job(repo, args.job))
    run = last_run(rec)
    if not run or run["status"] not in ACTIVE:
        raise DelegateError(f"job {args.job} is not running ({job_status(rec)})", EXIT_USAGE)
    # A request file, not a signal: the supervisor sees it whenever it looks,
    # even if it hasn't installed its handlers yet.
    (run_dir(repo, args.job, run["run"]) / "cancel").touch()
    repo.log("cancel", job=args.job, run=run["run"])
    return wait_for(repo, args.job, KILL_GRACE_S + 30)


def _finished_write_job(repo: Repo, job: str) -> dict:
    rec = refresh_status(repo, load_job(repo, job))
    if rec["mode"] != "write":
        raise DelegateError(f"job {job} is read-only — nothing to diff or merge", EXIT_USAGE)
    if job_status(rec) in ACTIVE:
        raise DelegateError(f"job {job} is still running", EXIT_RUNNING)
    return rec


def cmd_diff(repo: Repo, args) -> int:
    rec = _finished_write_job(repo, args.job)
    top, branch = repo.toplevel, rec["branch"]
    if rec.get("snapshot"):
        # Only the delegate's delta: `merge` applies exactly this.
        start = rec.get("merged_tip") or rec["base"]
        log_rng, diff_rng = f"{start}..{branch}", f"{start}..{branch}"
    else:
        # What `merge` would bring into this checkout, base commits included.
        log_rng, diff_rng = f"HEAD..{branch}", f"HEAD...{branch}"
    current = git(["rev-parse", "--abbrev-ref", "HEAD"], top)
    print(f"── what `merge {args.job}` would bring into {current} ──")
    print(git(["log", "--oneline", log_rng], top) or "(no commits)")
    print(git(["diff", "--stat", diff_rng], top))
    if args.patch:
        print(git(["diff", diff_rng], top))
    return EXIT_OK


def cmd_merge(repo: Repo, args) -> int:
    rec = _finished_write_job(repo, args.job)
    top, branch = repo.toplevel, rec["branch"]
    if top.resolve() == Path(rec["workdir"]).resolve():
        raise DelegateError("run merge from the checkout you want the work in, not the "
                            "delegate's worktree", EXIT_USAGE)
    if not unmerged_commits(repo, rec):
        raise DelegateError(f"job {args.job} has nothing new to merge", EXIT_USAGE)
    tip = branch_tip(repo, branch)
    if rec.get("snapshot"):
        # The branch starts from a snapshot of work that is still uncommitted
        # here, so apply only the delegate's delta on top of it.
        start = rec.get("merged_tip") or rec["base"]
        patch = subprocess.run(["git", "diff", "--binary", f"{start}..{tip}"], cwd=top,
                               capture_output=True, check=True).stdout
        proc = subprocess.run(["git", "apply", "--whitespace=nowarn"], cwd=top, input=patch,
                              capture_output=True)
        if proc.returncode != 0:
            raise DelegateError(
                "the delegate's changes don't apply cleanly (your files changed since the "
                f"snapshot): {proc.stderr.decode(errors='replace').strip()} — inspect with "
                f"`git diff {start} {branch}`")
        how = "applied to the working tree (uncommitted)"
    else:
        label = rec["target"]
        proc = subprocess.run(["git", "merge", "--no-ff", "--no-edit", "-m",
                               f"Merge {branch} (delegated to {label})", branch],
                              cwd=top, text=True, capture_output=True)
        if proc.returncode != 0:
            aborted = git_ok(["merge", "--abort"], top)
            raise DelegateError(
                "merge failed" + (" and was aborted — your branch is unchanged" if aborted
                                  else "") + f": {(proc.stdout + proc.stderr).strip()}")
        how = f"merged into {git(['rev-parse', '--abbrev-ref', 'HEAD'], top)}"
    update_job(repo, args.job, merged_tip=tip)
    repo.log("merge", job=args.job, how=how, tip=tip)
    emit({"job": args.job, "merged": True, "how": how,
          "next": [f"{script_hint()} discard {args.job}   # remove the worktree"]})
    return EXIT_OK


def cmd_discard(repo: Repo, args) -> int:
    rec = refresh_status(repo, load_job(repo, args.job))
    if job_status(rec) in ACTIVE:
        raise DelegateError(f"job {args.job} is still running — cancel it first", EXIT_RUNNING)
    if rec["mode"] == "write" and not args.force:
        problems = []
        unmerged = unmerged_commits(repo, rec)
        if unmerged:
            problems.append(f"{unmerged} unmerged commit(s)")
        dirty = uncommitted_in(Path(rec["workdir"]))
        if dirty:
            problems.append(f"{len(dirty)} uncommitted change(s) in the worktree")
        head = git(["symbolic-ref", "-q", "HEAD"], Path(rec["workdir"]), check=False) \
            if Path(rec["workdir"]).is_dir() else f"refs/heads/{rec['branch']}"
        if head != f"refs/heads/{rec['branch']}":
            problems.append(f"the worktree is on {head or 'a detached HEAD'}, not the job "
                            "branch")
        if problems:
            raise DelegateError(f"job {args.job} has {', '.join(problems)} — merge it, or "
                                "pass --force (after the user agrees) to throw the work away",
                                EXIT_CONFIRM)
    if rec["mode"] == "write":
        remove_worktree(repo, rec)
    shutil.rmtree(repo.job_dir(args.job))
    repo.log("discard", job=args.job, forced=bool(args.force))
    emit({"job": args.job, "discarded": True})
    return EXIT_OK


def cmd_doctor(repo: Repo, args) -> int:
    policy, source = load_policy(repo)
    report: dict = {
        "checkout": str(repo.toplevel), "state": str(repo.state),
        "host": detect_host(dict(os.environ)), "depth": effective_depth(repo),
        "policy_source": source,
        "policy": {k: v for k, v in policy.items() if k != "targets"},
        "running_jobs": running_count(repo), "targets": {},
    }
    for target in TARGETS:
        cfg = policy["targets"][target]
        info = {"enabled": cfg.get("enabled"), "version": cli_version(target)}
        info["installed"] = bool(info["version"])
        if target == "codex" and info["installed"]:
            works = codex_sandbox_works()
            info["sandbox_works"] = works
            if not works and cfg.get("sandbox") != "bypass":
                info["note"] = ("Codex's sandbox can't start here, so codex can't run "
                                "commands. Set targets.codex.sandbox to \"bypass\" in "
                                ".delegate/policy.json to rely on the worktree instead "
                                "(write jobs only; if this shell is itself sandboxed, re-run "
                                "doctor outside it)")
        if target == "agy":
            info["note"] = "read-only runs can read files but not run commands"
        if target == "copilot":
            info["note"] = "read-only runs can read files but not run shell commands"
        report["targets"][target] = info
    emit(report)
    return EXIT_OK


def operator_job(repo: Repo, policy: dict, args) -> dict:
    """The job an operator works in by hand: an existing one, or a new write job."""
    if job_exists(repo, args.job):
        return load_job(repo, args.job)
    target = check_target(args.to or "claude")
    with repo.lock():
        rec = new_job(repo, policy, args.job, "write", target)
        register_job(repo, rec, args.include_dirty, None)
    return rec


def cmd_shell(repo: Repo, args) -> int:
    """Operator-only: start the target CLI interactively in a job's worktree."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise DelegateError("`shell` is interactive — run it in your own terminal, not "
                            "from an agent", EXIT_REFUSED)
    policy, _ = load_policy(repo)
    rec = operator_job(repo, policy, args)
    repo.log("shell", job=rec["job"], target=rec["target"])
    print(f"[delegate] {rec['target']} in {rec['workdir']} — exit it to return",
          file=sys.stderr)
    os.chdir(rec["workdir"])
    env = child_env(dict(os.environ), rec["target"], pass_env=policy["pass_env"])
    os.execvpe(rec["target"], [rec["target"]], env)
    return EXIT_OK  # not reached


# ── CLI ───────────────────────────────────────────────────────────────


def _task_args(p: argparse.ArgumentParser, waits: bool) -> None:
    p.add_argument("--to", choices=TARGETS, help="target CLI")
    p.add_argument("--task", help="the task, verbatim")
    p.add_argument("--task-file", help="read the task from a file ('-' = stdin)")
    p.add_argument("--job", help="job name; reuse a finished job's name to follow up in it")
    p.add_argument("--mode", choices=MODES,
                   help="write: own worktree + branch (default); read-only: in place")
    p.add_argument("--model", help="model for the target CLI (default: its own default)")
    p.add_argument("--effort", help="reasoning effort, passed through to the target CLI")
    p.add_argument("--timeout", type=int, help="the job's wall-clock limit in seconds")
    p.add_argument("--resume", action="store_true",
                   help="continue the job's previous conversation (needs --job)")
    p.add_argument("--include-dirty", action="store_true",
                   help="start the worktree from your uncommitted changes too")
    p.add_argument("--base", help="start the worktree from this ref instead of HEAD")
    if waits:
        p.add_argument("--wait", type=int, default=540,
                       help="stop waiting after this many seconds (default 540); the job "
                            "keeps running")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="delegate.py", description="Hand a task to another coding-agent CLI, managed.",
        epilog="Exit codes: 0 ok, 1 failed, 2 usage, 3 refused by policy, 4 still running, "
               "5 target unavailable, 6 needs --force (ask the user).")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")
    _task_args(sub.add_parser("run", help="start a task and wait for its result"), True)
    _task_args(sub.add_parser("start", help="start a task in the background; returns at once"),
               False)
    p = sub.add_parser("wait", help="wait for a job and print its result")
    p.add_argument("job")
    p.add_argument("--timeout", type=int, default=540,
                   help="stop waiting after this many seconds (default 540)")
    p = sub.add_parser("status", help="print a job's latest (or given) run")
    p.add_argument("job")
    p.add_argument("--run", type=int)
    p = sub.add_parser("list", help="list jobs")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("log", help="show a run's raw output")
    p.add_argument("job")
    p.add_argument("--run", type=int)
    p.add_argument("--lines", type=int, default=60)
    sub.add_parser("cancel", help="stop a running job").add_argument("job")
    p = sub.add_parser("diff", help="show what merging a write job would bring")
    p.add_argument("job")
    p.add_argument("--patch", action="store_true", help="include the full patch")
    sub.add_parser("merge", help="bring a write job's work into this checkout").add_argument("job")
    p = sub.add_parser("discard", help="delete a job, its worktree and branch")
    p.add_argument("job")
    p.add_argument("--force", action="store_true",
                   help="also when it has unmerged or uncommitted work")
    sub.add_parser("doctor", help="report installed CLIs and the active policy")
    p = sub.add_parser("shell", help="operator only: open a target CLI in a job's worktree")
    p.add_argument("--job", required=True)
    p.add_argument("--to", choices=TARGETS)
    p.add_argument("--include-dirty", action="store_true")
    p = sub.add_parser("_supervise")
    p.add_argument("job")
    p.add_argument("run", type=int)
    return parser


COMMANDS = {
    "run": cmd_run, "start": cmd_start, "_supervise": cmd_supervise, "wait": cmd_wait,
    "status": cmd_status, "list": cmd_list, "log": cmd_log, "cancel": cmd_cancel,
    "diff": cmd_diff, "merge": cmd_merge, "discard": cmd_discard, "doctor": cmd_doctor,
    "shell": cmd_shell,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo = Repo(Path.cwd())
        return COMMANDS[args.cmd](repo, args)
    except DelegateError as e:
        emit({"error": str(e), **e.extra})
        return e.code
    except KeyboardInterrupt:
        emit({"error": "interrupted", "note": "a started job keeps running — check it with "
                                              "`list` or `wait`"})
        return 130


if __name__ == "__main__":
    sys.exit(main())
