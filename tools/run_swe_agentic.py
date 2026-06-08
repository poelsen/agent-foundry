#!/usr/bin/env python3
"""Agentic SWE benchmark — objective, judge-free.

Each task is a small self-contained repo with a failing pytest. For every
(task x model x skill-mode) we copy the task into a throwaway sandbox, let the
subject CLI fix it agentically (with tools), then run pytest. Score = test
pass/fail. No judge, so no judge bias — directly comparable across models.

Skill injection: a skill mode writes the skill's SKILL.md into the sandbox at
.github/skills/<skill>/ (Copilot loads these natively) so the agent can use it.

Usage:
    python3 tools/run_swe_agentic.py --model gpt-5.5 --skill megamind-deep
    python3 tools/run_swe_agentic.py --model claude-opus-4.7 --workers 2 --save results/swe-opus47.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TASKS_DIR = REPO_ROOT / "tests" / "swe_tasks"
SKILLS_DIR = REPO_ROOT / "cli" / "claude" / "skills"

PROMPT_TEMPLATE = (
    "This project has a failing test suite. Read the code and the tests, find "
    "the bug, and fix the source so all tests pass. Do not edit the tests. "
    "Run `python -m pytest -q` to check your work.\n\n"
    "Bug report:\n{report}\n"
)
SKILL_NUDGE = (
    "\nBefore editing, apply the `{skill}` reasoning skill available to you: "
    "reason through the problem systematically first, then fix.\n"
)


def discover_tasks(only: list[str] | None) -> list[Path]:
    tasks = sorted(p for p in TASKS_DIR.iterdir() if p.is_dir() and (p / "PROMPT.md").exists())
    if only:
        tasks = [t for t in tasks if t.name in only]
    return tasks


def _inject_skill(sandbox: Path, skill: str) -> None:
    """Drop the skill's SKILL.md into the sandbox so Copilot loads it."""
    src = SKILLS_DIR / skill / "SKILL.md"
    if not src.exists():
        return
    dest_dir = sandbox / ".github" / "skills" / skill
    dest_dir.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8")
    # Strip the Claude-only `model:` frontmatter line (unsupported by Copilot).
    text = re.sub(r"^\s*model\s*:.*$\n?", "", text, flags=re.MULTILINE)
    (dest_dir / "SKILL.md").write_text(text, encoding="utf-8")


def _run_pytest(cwd: Path) -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        capture_output=True, text=True, cwd=cwd, timeout=300,
    )
    out = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, (out[-1] if out else "")


def run_one(task: Path, model: str, skill: str | None) -> dict:
    """Run one (task, model, skill) combo in a sandbox; return a result dict."""
    report = (task / "PROMPT.md").read_text(encoding="utf-8").strip()
    with tempfile.TemporaryDirectory(prefix="swe-") as td:
        sandbox = Path(td)
        for item in task.iterdir():
            if item.name == "PROMPT.md":
                continue
            dest = sandbox / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # Confirm the suite genuinely starts red (guards against a broken task).
        starts_red = not _run_pytest(sandbox)[0]

        prompt = PROMPT_TEMPLATE.format(report=report)
        if skill:
            _inject_skill(sandbox, skill)
            prompt += SKILL_NUDGE.format(skill=skill)

        copilot = shutil.which("copilot")
        agent_err = ""
        try:
            r = subprocess.run(
                [copilot, "-p", prompt, "--model", model, "--allow-all-tools", "-s", "--no-color"],
                capture_output=True, text=True, cwd=sandbox, timeout=900,
            )
            if r.returncode != 0:
                agent_err = (r.stderr or r.stdout).strip()[:200]
        except subprocess.TimeoutExpired:
            agent_err = "agent timeout"

        passed, summary = _run_pytest(sandbox)
    return {
        "task": task.name, "model": model, "skill": skill or "baseline",
        "passed": passed, "starts_red": starts_red,
        "pytest": summary, "agent_err": agent_err,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Agentic SWE benchmark (test-pass scored)")
    ap.add_argument("--model", required=True, help="Copilot model id (e.g. gpt-5.5, claude-opus-4.7)")
    ap.add_argument("--skill", nargs="*", default=[None],
                    help="Skill modes to test (baseline always included)")
    ap.add_argument("--tasks", nargs="*", help="Specific task ids")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--save", type=str)
    args = ap.parse_args()

    if not shutil.which("copilot"):
        print("ERROR: copilot CLI not found in PATH")
        sys.exit(1)

    modes: list[str | None] = [None]
    for s in args.skill:
        if s and s != "None" and s not in modes:
            modes.append(s)

    tasks = discover_tasks(args.tasks)
    if not tasks:
        print(f"No tasks found in {TASKS_DIR}")
        sys.exit(1)

    combos = [(t, args.model, m) for t in tasks for m in modes]
    print(f"Agentic SWE: {len(tasks)} tasks x {len(modes)} modes | model={args.model} "
          f"| workers={args.workers} | {len(combos)} runs")

    results: list[dict] = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(run_one, t, mdl, sk): (t, sk) for (t, mdl, sk) in combos}
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            flag = "" if res["starts_red"] else " [WARN: task did not start red]"
            print(f"  {res['task']:18s} {res['skill']:20s} "
                  f"{'PASS' if res['passed'] else 'FAIL'}  ({res['pytest']}){flag}")

    print(f"\nCompleted in {time.time() - start:.0f}s")
    # Summary: pass rate per mode
    print("\n  mode                 pass-rate")
    for m in modes:
        label = m or "baseline"
        rs = [r for r in results if r["skill"] == label]
        p = sum(1 for r in rs if r["passed"])
        print(f"  {label:20s} {p}/{len(rs)}")

    if args.save:
        Path(args.save).write_text(json.dumps({
            "model": args.model, "modes": [m or "baseline" for m in modes],
            "results": results,
        }, indent=2), encoding="utf-8")
        print(f"\nSaved → {args.save}")


if __name__ == "__main__":
    main()
