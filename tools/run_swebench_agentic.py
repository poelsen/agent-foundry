#!/usr/bin/env python3
"""Agentic SWE-bench Verified harness — objective, judge-free.

For each (instance x model x skill): clone the repo at its base commit, let
the model fix the issue agentically via `copilot --allow-all-tools` (it sees
only the problem statement, not the gold tests), capture `git diff` as the
prediction, then evaluate with the official SWE-bench Docker harness
(resolved = the hidden FAIL_TO_PASS tests pass and PASS_TO_PASS still pass).

Two phases: build predictions (agent), then evaluate (Docker). Use
--agent-only / --eval-only to run them separately.

Usage:
    python3 tools/run_swebench_agentic.py --model gpt-5.5 \
        --instances pallets__flask-5014 psf__requests-6028 --workers 2
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
SKILLS_DIR = REPO_ROOT / "cli" / "claude" / "skills"
OUT_DIR = REPO_ROOT / "results" / "swebench"
DATASET = "princeton-nlp/SWE-bench_Verified"


def _load_instances(instance_ids: list[str]) -> dict[str, dict]:
    from datasets import load_dataset
    ds = load_dataset(DATASET, split="test")
    wanted = set(instance_ids)
    return {r["instance_id"]: r for r in ds if r["instance_id"] in wanted}


def _inject_skill(repo_dir: Path, skill: str) -> None:
    src = SKILLS_DIR / skill / "SKILL.md"
    if not src.exists():
        return
    dest = repo_dir / ".github" / "skills" / skill
    dest.mkdir(parents=True, exist_ok=True)
    text = re.sub(r"^\s*model\s*:.*$\n?", "", src.read_text(encoding="utf-8"),
                  flags=re.MULTILINE)
    (dest / "SKILL.md").write_text(text, encoding="utf-8")


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def make_prediction(inst: dict, model: str, skill: str | None) -> dict:
    """Clone at base commit, run the agent, return a SWE-bench prediction dict."""
    repo = inst["repo"]
    base = inst["base_commit"]
    model_name = f"{model}__{skill or 'baseline'}"
    with tempfile.TemporaryDirectory(prefix="sweb-") as td:
        work = Path(td) / "repo"
        clone = _git(["clone", "--quiet", "--filter=blob:none",
                      f"https://github.com/{repo}.git", str(work)], Path(td))
        if clone.returncode != 0:
            return {"instance_id": inst["instance_id"], "model_name_or_path": model_name,
                    "model_patch": "", "error": f"clone failed: {clone.stderr[:160]}"}
        _git(["checkout", "--quiet", base], work)
        # Pin identity so the agent's commits (if any) don't error; we diff anyway.
        _git(["config", "user.email", "bench@local"], work)
        _git(["config", "user.name", "bench"], work)

        prompt = (
            "You are fixing a real bug in this repository. Resolve the following "
            "issue by editing the source code. Do NOT edit or add tests — the "
            "hidden test suite will judge you. Make the smallest correct change.\n\n"
            f"ISSUE:\n{inst['problem_statement']}\n"
        )
        if skill:
            _inject_skill(work, skill)
            prompt += f"\nApply the `{skill}` reasoning skill: analyze before editing.\n"

        copilot = shutil.which("copilot")
        err = ""
        try:
            r = subprocess.run(
                [copilot, "-p", prompt, "--model", model, "--allow-all-tools", "-s", "--no-color"],
                cwd=work, capture_output=True, text=True, timeout=1200,
            )
            if r.returncode != 0:
                err = (r.stderr or r.stdout).strip()[:160]
        except subprocess.TimeoutExpired:
            err = "agent timeout"

        # Capture the source diff (exclude the injected skill dir).
        if (work / ".github" / "skills").exists():
            shutil.rmtree(work / ".github" / "skills", ignore_errors=True)
        _git(["add", "-A"], work)
        diff = _git(["diff", "--cached", base], work).stdout
        return {"instance_id": inst["instance_id"], "model_name_or_path": model_name,
                "model_patch": diff, "error": err}


def run_eval(preds_path: Path, instance_ids: list[str], run_id: str, workers: int) -> Path | None:
    """Invoke the SWE-bench Docker harness; return the report json path."""
    cmd = [sys.executable, "-m", "swebench.harness.run_evaluation",
           "--dataset_name", DATASET, "--predictions_path", str(preds_path),
           "--instance_ids", *instance_ids, "--run_id", run_id,
           "--max_workers", str(workers)]
    print(f"  eval: {' '.join(cmd[3:])}")
    subprocess.run(cmd, cwd=REPO_ROOT)
    # Report is written as <model_name_or_path>.<run_id>.json in CWD.
    model_name = json.loads(preds_path.read_text().splitlines()[0])["model_name_or_path"]
    report = REPO_ROOT / f"{model_name}.{run_id}.json"
    return report if report.exists() else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Agentic SWE-bench Verified harness")
    ap.add_argument("--model", required=True)
    ap.add_argument("--skill", nargs="*", default=[None])
    ap.add_argument("--instances", nargs="+", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--agent-only", action="store_true")
    ap.add_argument("--eval-only", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    modes: list[str | None] = [None]
    for s in args.skill:
        if s and s != "None" and s not in modes:
            modes.append(s)

    insts = _load_instances(args.instances)
    missing = set(args.instances) - set(insts)
    if missing:
        print(f"WARNING: instances not in dataset: {missing}")

    for skill in modes:
        tag = f"{args.model}-{skill or 'baseline'}".replace("/", "_")
        preds_path = OUT_DIR / f"preds-{tag}.jsonl"
        if not args.eval_only:
            print(f"\n=== AGENT phase: model={args.model} skill={skill or 'baseline'} ===")
            preds: list[dict] = []
            start = time.time()
            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
                futs = {ex.submit(make_prediction, insts[i], args.model, skill): i
                        for i in args.instances if i in insts}
                for fut in as_completed(futs):
                    p = fut.result()
                    preds.append(p)
                    plen = len(p["model_patch"])
                    print(f"  {p['instance_id']:32s} patch={plen:5d}b "
                          f"{'ERR:' + p['error'] if p.get('error') else ''}")
            preds_path.write_text("\n".join(json.dumps(p) for p in preds) + "\n")
            print(f"  agent phase done in {time.time() - start:.0f}s → {preds_path}")
        if not args.agent_only:
            print(f"\n=== EVAL phase: {tag} ===")
            report = run_eval(preds_path, args.instances, f"agentic-{tag}", args.workers)
            if report:
                data = json.loads(report.read_text())
                print(f"  RESOLVED {data['resolved_instances']}/{data['total_instances']} "
                      f"| errors={data['error_instances']} | report={report.name}")


if __name__ == "__main__":
    main()
