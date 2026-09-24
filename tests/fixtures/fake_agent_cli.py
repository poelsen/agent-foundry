#!/usr/bin/env python3
"""Stand-in for the claude / codex / agy / copilot CLIs in delegate tests.

Installed under each CLI's name (FAKE_CLI_NAME); the name picks the output format, which
mirrors what the real CLIs print in non-interactive JSON mode. Behavior is
driven by env vars:

  FAKE_CLI_ACTION   write | artifacts | commit | commit2 | checkout | background |
                    stubborn | fail | sleep | none (default write)
  FAKE_CLI_SLEEP    seconds to sleep for the sleep action
  FAKE_CLI_RECORD   file to append one JSON line per call (argv, cwd, env, prompt)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

name = os.environ.get("FAKE_CLI_NAME") or Path(sys.argv[0]).name
args = sys.argv[1:]

if args == ["--version"]:
    print(f"{name} 9.9.9")
    sys.exit(0)
if name == "codex" and args[:1] == ["sandbox"]:
    sys.exit(0)


def arg_after(flag: str) -> str | None:
    return args[args.index(flag) + 1] if flag in args else None


prompt = sys.stdin.read() if name in ("claude", "codex") else (arg_after("-p") or "")
record = os.environ.get("FAKE_CLI_RECORD")
if record:
    keep = {k: v for k, v in os.environ.items()
            if k.startswith(("FOUNDRY_DELEGATE_", "ANTHROPIC_", "OPENAI_", "CLAUDE", "CODEX_",
                             "ANTIGRAVITY_", "COPILOT_", "AI_AGENT"))}
    with Path(record).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cli": name, "argv": args, "cwd": str(Path.cwd()), "env": keep,
                             "prompt": prompt}) + "\n")

action = os.environ.get("FAKE_CLI_ACTION", "write")
if action == "sleep":
    time.sleep(float(os.environ.get("FAKE_CLI_SLEEP", "30")))
elif action == "stubborn":
    import signal
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(float(os.environ.get("FAKE_CLI_SLEEP", "30")))
elif action == "background":
    # A leftover background process in the same process group.
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    Path("delegated.txt").write_text(f"written by {name}\n", encoding="utf-8")
elif action == "commit2":
    Path("second.txt").write_text("second run\n", encoding="utf-8")
    subprocess.run(["git", "add", "second.txt"], check=True)
    subprocess.run(["git", "-c", "user.name=fake", "-c", "user.email=f@f", "commit", "-qm",
                    "second run"], check=True)
elif action == "artifacts":
    Path("delegated.txt").write_text(f"written by {name}\n", encoding="utf-8")
    Path("__pycache__").mkdir(exist_ok=True)
    Path("__pycache__/delegated.cpython-312.pyc").write_bytes(b"\0")
elif action in ("write", "commit"):
    Path("delegated.txt").write_text(f"written by {name}\n", encoding="utf-8")
    if action == "commit":
        subprocess.run(["git", "add", "delegated.txt"], check=True)
        subprocess.run(["git", "-c", "user.name=fake", "-c", "user.email=f@f", "commit", "-qm",
                        "fake commit"], check=True)
elif action == "checkout":
    subprocess.run(["git", "checkout", "-qb", "sneaky"], check=True)
    Path("delegated.txt").write_text("on the wrong branch\n", encoding="utf-8")
elif action == "fail":
    print(f"{name}: simulated failure", file=sys.stderr)
    sys.exit(1)

answer = f"{name} finished the task"
if name == "claude":
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                      "result": answer, "session_id": "sess-claude", "num_turns": 2,
                      "total_cost_usd": 0.01, "permission_denials": []}))
elif name == "codex":
    out = arg_after("-o")
    if out:
        Path(out).write_text(answer, encoding="utf-8")
    for event in ({"type": "thread.started", "thread_id": "thread-codex"},
                  {"type": "turn.started"},
                  {"type": "item.completed", "item": {"type": "agent_message", "text": answer}},
                  {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}):
        print(json.dumps(event))
elif name == "agy":
    response = "" if action == "none" else answer
    print(json.dumps({"conversation_id": "conv-agy", "status": "SUCCESS", "response": response,
                      "usage": "{'input_tokens': 5, 'output_tokens': 1}"}))
    if not response:
        print("jetski: no output produced — a tool required the \"command\" permission",
              file=sys.stderr)
elif name == "copilot":
    for event in ({"type": "assistant.message", "data": {"content": "", "toolRequests": [{}]}},
                  {"type": "assistant.message", "data": {"content": answer}},
                  {"type": "result", "sessionId": "sess-copilot", "exitCode": 0,
                   "usage": {"premiumRequests": 1}}):
        print(json.dumps(event))
