#!/usr/bin/env python3
"""Run comprehensive megamind skill benchmarks.

Runs every challenge against every skill mode + baseline.
Produces a detailed comparison report. Subject and judge each run via the
claude or copilot CLI (configurable); supports a second judge for
disagreement flagging.

Usage:
    python3 tools/run_benchmark.py --runs 2
    python3 tools/run_benchmark.py --skill megamind-deep --runs 2
    python3 tools/run_benchmark.py --save results/baseline.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent))

from eval_rubric import Challenge, EvalResult, load_challenges, score_response
from eval_runner import (
    _build_depth_judge_prompt,
    _build_judge_prompt,
    _build_outcome_judge_prompt,
    _build_subject_prompt,
    _parse_depth_response,
    _parse_judge_response,
    _parse_outcome_response,
)
from skill_parser import parse_skill

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "cli" / "claude" / "skills"
CHALLENGES_DIR = REPO_ROOT / "tests" / "challenges"

# Backend = which CLI runs the prompt: "claude" or "copilot". Model = the
# model id for that CLI. Both subject (the skill under test) and judge are
# independently configurable via CLI flags; defaults set in main().
SUBJECT_BACKEND = "claude"
SUBJECT_MODEL = "opus"
JUDGE_BACKEND = "claude"
JUDGE_MODEL = "opus"
# Optional second judge for dual-judge mode (None = single judge).
JUDGE2_BACKEND: str | None = None
JUDGE2_MODEL: str | None = None
# Judges "disagree" if pass/fail differs or |scoreA - scoreB| exceeds this.
JUDGE_DISAGREE_THRESHOLD = 2

ALL_SKILL_MODES = [
    None, "megamind-deep", "megamind-creative", "megamind-adversarial", "megamind-financial",
]


def label(skill: str | None) -> str:
    return skill or "baseline"


def load_skill_content(skill_name: str) -> str | None:
    path = SKILLS_DIR / skill_name / "SKILL.md"
    if not path.exists():
        return None
    return parse_skill(path).body


def _claude_cli(prompt: str, model: str = "opus") -> str:
    """Run a prompt through the claude CLI in non-interactive mode.

    Uses --output-format json for structured output and --permission-mode
    bypassPermissions for non-interactive / CI use.
    """
    claude_bin = shutil.which("claude")
    if not claude_bin:
        raise RuntimeError("claude CLI not found in PATH")

    # Strip ANTHROPIC_API_KEY so the CLI uses OAuth, not a potentially stale key
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    result = subprocess.run(
        [
            claude_bin,
            "--print",
            "--output-format", "json",
            "--model", model,
            "--no-session-persistence",
            "--permission-mode", "bypassPermissions",
            "--tools", "",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=1200,
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {result.stderr.strip()}")

    # --output-format json wraps the response in a JSON object
    try:
        data = json.loads(result.stdout)
        # The JSON format returns {"type": "result", "result": "..."}
        if isinstance(data, dict) and "result" in data:
            return data["result"].strip()
        # Fallback: if format differs, return raw text content
        return result.stdout.strip()
    except json.JSONDecodeError:
        # Fallback for non-JSON output
        return result.stdout.strip()


def _copilot_cli(prompt: str, model: str) -> str:
    """Run a prompt through the GitHub Copilot CLI, non-interactively.

    No tools are enabled (pure text generation) and the call runs in a
    throwaway temp cwd, so a benchmark prompt can never touch the repo.
    """
    copilot_bin = shutil.which("copilot")
    if not copilot_bin:
        raise RuntimeError("copilot CLI not found in PATH")

    with tempfile.TemporaryDirectory(prefix="bench-copilot-") as td:
        result = subprocess.run(
            [copilot_bin, "-p", prompt, "--model", model, "-s", "--no-color"],
            capture_output=True,
            text=True,
            timeout=1200,
            cwd=td,
        )

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"copilot CLI failed ({model}): {detail}")
    return result.stdout.strip()


def _invoke(prompt: str, backend: str, model: str) -> str:
    """Dispatch a prompt to the configured backend CLI."""
    if backend == "copilot":
        return _copilot_cli(prompt, model)
    return _claude_cli(prompt, model)


def _judge_response(
    challenge: Challenge, response: str, skill_name: str | None,
    backend: str, model: str,
) -> EvalResult:
    """Score a single subject response with one judge (backend/model)."""
    judge_prompt = _build_judge_prompt(challenge, response)
    judge_text = _invoke(judge_prompt, backend, model)
    element_scores, anti_scores = _parse_judge_response(challenge, judge_text)

    # Separate depth judge call (avoids halo effect from binary scoring)
    depth_scores = []
    if challenge.rubric.depth_elements:
        depth_prompt = _build_depth_judge_prompt(challenge, response)
        depth_text = _invoke(depth_prompt, backend, model)
        depth_scores = _parse_depth_response(challenge, depth_text)

    # Separate outcome judge call (process-blind, tests decision quality)
    outcome_scores = []
    if challenge.rubric.outcome_elements:
        outcome_prompt = _build_outcome_judge_prompt(challenge, response)
        outcome_text = _invoke(outcome_prompt, backend, model)
        outcome_scores = _parse_outcome_response(challenge, outcome_text)

    return score_response(
        challenge, element_scores, anti_scores,
        skill_used=skill_name, raw_response=response,
        depth_scores=depth_scores,
        outcome_scores=outcome_scores,
    )


def run_one(challenge: Challenge, skill_name: str | None) -> EvalResult:
    """Run a single challenge/skill combo.

    Subject and judge use independently configured backends/models. When a
    second judge is configured (JUDGE2_*), the same response is scored by both
    and the result carries judge2_score/judge2_passed/judges_agree so
    disagreements can be flagged for human review.
    """
    skill_content = load_skill_content(skill_name) if skill_name else None
    subject_prompt = _build_subject_prompt(challenge, skill_content)
    response = _invoke(subject_prompt, SUBJECT_BACKEND, SUBJECT_MODEL)

    result = _judge_response(challenge, response, skill_name, JUDGE_BACKEND, JUDGE_MODEL)

    if JUDGE2_BACKEND and JUDGE2_MODEL:
        r2 = _judge_response(challenge, response, skill_name, JUDGE2_BACKEND, JUDGE2_MODEL)
        agree = (result.passed == r2.passed
                 and abs(result.total_score - r2.total_score) <= JUDGE_DISAGREE_THRESHOLD)
        result = dataclasses.replace(
            result, judge2_score=r2.total_score, judge2_passed=r2.passed, judges_agree=agree)

    return result


# ── Serialization ──


def results_to_json(
    challenges: list[Challenge],
    all_results: dict[str, dict[str, list[EvalResult]]],
    skill_modes: list[str | None],
) -> dict:
    """Convert results to a JSON-serializable dict."""
    data: dict = {"challenges": {}, "skill_modes": [label(s) for s in skill_modes]}
    for challenge in challenges:
        cdata: dict = {"name": challenge.name, "modes": {}}
        for skill in skill_modes:
            key = label(skill)
            results = all_results.get(challenge.id, {}).get(key, [])
            mode_data: dict = {
                "scores": [r.total_score for r in results],
                "passed": [r.passed for r in results],
                "elements": {},
                "anti_patterns": {},
            }
            # Dual-judge fields (present only when a second judge ran)
            if any(r.judge2_score is not None for r in results):
                mode_data["judge2_scores"] = [r.judge2_score for r in results]
                mode_data["judge2_passed"] = [r.judge2_passed for r in results]
                mode_data["judges_agree"] = [r.judges_agree for r in results]
            for eid in challenge.rubric.required_elements:
                hits = sum(
                    1 for r in results
                    for e in r.element_scores
                    if e.element_id == eid and e.present
                )
                mode_data["elements"][eid] = {"hits": hits, "total": len(results)}
            for aid in challenge.rubric.anti_patterns:
                hits = sum(
                    1 for r in results
                    for a in r.anti_pattern_scores
                    if a.element_id == aid and a.present
                )
                mode_data["anti_patterns"][aid] = {"hits": hits, "total": len(results)}
            if challenge.rubric.depth_elements:
                mode_data["depth"] = {}
                for did in challenge.rubric.depth_elements:
                    depths = [
                        d.score for r in results for d in r.depth_scores
                        if d.element_id == did
                    ]
                    mode_data["depth"][did] = {
                        "avg": sum(depths) / len(depths) if depths else 0,
                        "scores": depths,
                    }
            cdata["modes"][key] = mode_data
        data["challenges"][challenge.id] = cdata
    return data


def load_saved_results(path: Path) -> dict:
    """Load previously saved benchmark results."""
    return json.loads(path.read_text(encoding="utf-8"))


# ── Reporting ──


def print_header(text: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {text}")
    print(f"{'=' * 80}")


def _element_hit_rate(
    results: list[EvalResult], element_id: str, is_anti: bool = False
) -> tuple[int, int]:
    """Return (hits, total) for an element across results."""
    scores_attr = "anti_pattern_scores" if is_anti else "element_scores"
    hits = sum(
        1 for r in results
        for e in getattr(r, scores_attr)
        if e.element_id == element_id and e.present
    )
    return hits, len(results)


def _variance(scores: list[int]) -> float:
    """Compute variance of scores."""
    if len(scores) < 2:
        return 0.0
    avg = sum(scores) / len(scores)
    return sum((s - avg) ** 2 for s in scores) / (len(scores) - 1)


def print_element_grid(
    challenges: list[Challenge],
    all_results: dict[str, dict[str, list[EvalResult]]],
    skill_modes: list[str | None],
) -> None:
    """Print per-element scoring grid for each challenge."""
    for challenge in challenges:
        print_header(f"{challenge.id}: {challenge.name}")
        print(f"  Category: {challenge.category}")
        print(f"  Passing score: {challenge.rubric.passing_score}")
        print()

        modes = [label(s) for s in skill_modes]
        col_width = 16
        header = "  Element".ljust(34) + "".join(m.center(col_width) for m in modes)
        print(header)
        print("  " + "-" * (32 + col_width * len(modes)))

        # Required elements
        for eid in challenge.rubric.required_elements:
            row = f"  + {eid}".ljust(34)
            for skill in skill_modes:
                results = all_results.get(challenge.id, {}).get(label(skill), [])
                if results:
                    hits, total = _element_hit_rate(results, eid)
                    pct = hits / total if total else 0
                    marker = " **" if pct == 0 else ""  # Flag 0% hit rate
                    cell = f"{hits}/{total} ({pct:.0%}){marker}"
                else:
                    cell = "-"
                row += cell.center(col_width)
            print(row)

        # Anti-patterns
        if challenge.rubric.anti_patterns:
            print()
            for aid in challenge.rubric.anti_patterns:
                row = f"  ! {aid}".ljust(34)
                for skill in skill_modes:
                    results = all_results.get(challenge.id, {}).get(label(skill), [])
                    if results:
                        hits, total = _element_hit_rate(results, aid, is_anti=True)
                        pct = hits / total if total else 0
                        marker = " !!" if pct == 1.0 else ""  # Flag 100% anti-pattern
                        cell = f"{hits}/{total} ({pct:.0%}){marker}"
                    else:
                        cell = "-"
                    row += cell.center(col_width)
                print(row)

        # Score + variance
        print()
        row = "  SCORE (avg)".ljust(34)
        for skill in skill_modes:
            results = all_results.get(challenge.id, {}).get(label(skill), [])
            if results:
                scores = [r.total_score for r in results]
                avg = sum(scores) / len(scores)
                var = _variance(scores)
                cell = f"{avg:.1f} (var={var:.1f})"
            else:
                cell = "-"
            row += cell.center(col_width)
        print(row)

        row = "  PASS RATE".ljust(34)
        for skill in skill_modes:
            results = all_results.get(challenge.id, {}).get(label(skill), [])
            if results:
                rate = sum(1 for r in results if r.passed) / len(results)
                cell = f"{rate:.0%}"
            else:
                cell = "-"
            row += cell.center(col_width)
        print(row)

        # Depth scores (only if challenge has depth_elements)
        if challenge.rubric.depth_elements:
            print()
            print("  DEPTH (0-3 scale, indicative — average across runs):")
            for did in challenge.rubric.depth_elements:
                row = f"  ~ {did}".ljust(34)
                for skill in skill_modes:
                    results = all_results.get(challenge.id, {}).get(label(skill), [])
                    if results:
                        depths = [
                            d.score for r in results for d in r.depth_scores
                            if d.element_id == did
                        ]
                        if depths:
                            avg_d = sum(depths) / len(depths)
                            cell = f"{avg_d:.1f}/3"
                        else:
                            cell = "n/a"
                    else:
                        cell = "-"
                    row += cell.center(col_width)
                print(row)

            row = "  DEPTH TOTAL (avg)".ljust(34)
            for skill in skill_modes:
                results = all_results.get(challenge.id, {}).get(label(skill), [])
                if results:
                    totals = [r.depth_total for r in results]
                    max_depth = len(challenge.rubric.depth_elements) * 3
                    avg_t = sum(totals) / len(totals) if totals else 0
                    cell = f"{avg_t:.1f}/{max_depth}"
                else:
                    cell = "-"
                row += cell.center(col_width)
            print(row)

        # Outcome scores (process-blind, only if challenge has outcome_elements)
        if challenge.rubric.outcome_elements:
            print()
            print("  OUTCOMES (process-blind — did it change the decision?):")
            for oid in challenge.rubric.outcome_elements:
                row = f"  * {oid}".ljust(34)
                for skill in skill_modes:
                    results = all_results.get(challenge.id, {}).get(label(skill), [])
                    if results:
                        met = sum(
                            1 for r in results for o in r.outcome_scores
                            if o.element_id == oid and o.met
                        )
                        total = len(results)
                        cell = f"{met}/{total}"
                    else:
                        cell = "-"
                    row += cell.center(col_width)
                print(row)

        print()


def print_summary_table(
    challenges: list[Challenge],
    all_results: dict[str, dict[str, list[EvalResult]]],
    skill_modes: list[str | None],
) -> None:
    """Print overall summary comparison table."""
    print_header("OVERALL SUMMARY")

    col_width = 16
    modes = [label(s) for s in skill_modes]
    header = "  Metric".ljust(28) + "".join(m.center(col_width) for m in modes)
    print(header)
    print("  " + "-" * (26 + col_width * len(modes)))

    # Avg score
    row = "  Avg Score".ljust(28)
    for skill in skill_modes:
        scores = [
            r.total_score
            for cid in all_results
            for r in all_results[cid].get(label(skill), [])
        ]
        avg = sum(scores) / len(scores) if scores else 0
        row += f"{avg:.1f}".center(col_width)
    print(row)

    # Variance
    row = "  Score Variance".ljust(28)
    for skill in skill_modes:
        scores = [
            r.total_score
            for cid in all_results
            for r in all_results[cid].get(label(skill), [])
        ]
        var = _variance(scores) if scores else 0
        row += f"{var:.1f}".center(col_width)
    print(row)

    # Pass rate
    row = "  Pass Rate".ljust(28)
    for skill in skill_modes:
        results = [
            r for cid in all_results for r in all_results[cid].get(label(skill), [])
        ]
        rate = sum(1 for r in results if r.passed) / len(results) if results else 0
        row += f"{rate:.0%}".center(col_width)
    print(row)

    # Delta vs baseline
    baseline_scores = [
        r.total_score
        for cid in all_results
        for r in all_results[cid].get("baseline", [])
    ]
    baseline_avg = sum(baseline_scores) / len(baseline_scores) if baseline_scores else 0

    row = "  Delta vs Baseline".ljust(28)
    for skill in skill_modes:
        if skill is None:
            row += "-".center(col_width)
        else:
            scores = [
                r.total_score
                for cid in all_results
                for r in all_results[cid].get(label(skill), [])
            ]
            avg = sum(scores) / len(scores) if scores else 0
            delta = avg - baseline_avg
            sign = "+" if delta >= 0 else ""
            row += f"{sign}{delta:.1f}".center(col_width)
    print(row)

    # Per-challenge breakdown
    print()
    print("  Per-challenge scores:")
    row = "  Challenge".ljust(28) + "".join(m.center(col_width) for m in modes)
    print(row)
    print("  " + "-" * (26 + col_width * len(modes)))

    for challenge in challenges:
        row = f"  {challenge.id}".ljust(28)
        for skill in skill_modes:
            results = all_results.get(challenge.id, {}).get(label(skill), [])
            if results:
                avg = sum(r.total_score for r in results) / len(results)
                row += f"{avg:.1f}".center(col_width)
            else:
                row += "-".center(col_width)
        print(row)

    # Weakness report: elements where any skill scores 0%
    print()
    print_header("WEAKNESS REPORT (0% hit rate elements)")
    found_weakness = False
    for challenge in challenges:
        for skill in skill_modes:
            if skill is None:
                continue
            results = all_results.get(challenge.id, {}).get(label(skill), [])
            if not results:
                continue
            for eid in challenge.rubric.required_elements:
                hits, total = _element_hit_rate(results, eid)
                if hits == 0 and total > 0:
                    print(f"  {label(skill)} on {challenge.id}: {eid} = 0/{total}")
                    found_weakness = True
    if not found_weakness:
        print("  None found!")

    # Anti-pattern report: elements where any skill scores 100%
    print()
    print_header("ANTI-PATTERN ALERT (100% trigger rate)")
    found_alert = False
    for challenge in challenges:
        for skill in skill_modes:
            if skill is None:
                continue
            results = all_results.get(challenge.id, {}).get(label(skill), [])
            if not results:
                continue
            for aid in challenge.rubric.anti_patterns:
                hits, total = _element_hit_rate(results, aid, is_anti=True)
                if hits == total and total > 0:
                    print(f"  {label(skill)} on {challenge.id}: {aid} = {hits}/{total}")
                    found_alert = True
    if not found_alert:
        print("  None found!")

    print()


def print_comparison(current: dict, saved: dict) -> None:
    """Print comparison between current and saved results."""
    print_header("COMPARISON WITH SAVED BASELINE")

    for cid, cdata in current.get("challenges", {}).items():
        saved_cdata = saved.get("challenges", {}).get(cid)
        if not saved_cdata:
            print(f"\n  {cid}: NEW (no saved baseline)")
            continue

        print(f"\n  {cid}: {cdata.get('name', '')}")
        for mode_key, mode_data in cdata.get("modes", {}).items():
            saved_mode = saved_cdata.get("modes", {}).get(mode_key)
            if not saved_mode:
                continue

            cur_scores = mode_data.get("scores", [])
            sav_scores = saved_mode.get("scores", [])
            cur_avg = sum(cur_scores) / len(cur_scores) if cur_scores else 0
            sav_avg = sum(sav_scores) / len(sav_scores) if sav_scores else 0
            delta = cur_avg - sav_avg
            if abs(delta) < 0.01:
                continue

            sign = "+" if delta >= 0 else ""
            print(f"    {mode_key}: {sav_avg:.1f} -> {cur_avg:.1f} ({sign}{delta:.1f})")

            # Element-level diffs
            for eid, edata in mode_data.get("elements", {}).items():
                saved_edata = saved_mode.get("elements", {}).get(eid)
                if not saved_edata:
                    continue
                cur_rate = edata["hits"] / edata["total"] if edata["total"] else 0
                sav_rate = saved_edata["hits"] / saved_edata["total"] if saved_edata["total"] else 0
                if abs(cur_rate - sav_rate) > 0.01:
                    print(f"      {eid}: {sav_rate:.0%} -> {cur_rate:.0%}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run megamind skill benchmarks")
    parser.add_argument("--runs", type=int, default=2, help="Runs per challenge/skill combo")
    parser.add_argument("--challenges", nargs="*", help="Specific challenge IDs to run")
    parser.add_argument("--skill", nargs="*", help="Specific skills to test (always includes baseline)")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--save", type=str, help="Save results to JSON file")
    parser.add_argument("--compare", type=str, help="Compare with saved baseline JSON")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers")
    parser.add_argument("--subject-backend", choices=["claude", "copilot"], default="claude",
                        help="CLI that runs the skill under test")
    parser.add_argument("--subject-model", type=str, default=None,
                        help="Model id for the subject backend (e.g. gpt-5.5, claude-opus-4.7)")
    parser.add_argument("--judge-backend", choices=["claude", "copilot"], default="claude",
                        help="CLI that runs the judge (keep fixed for fair cross-model scoring)")
    parser.add_argument("--judge-model", type=str, default=None,
                        help="Model id for the judge backend")
    parser.add_argument("--judge2-backend", choices=["claude", "copilot"], default=None,
                        help="Second judge backend (enables dual-judge + disagreement flagging)")
    parser.add_argument("--judge2-model", type=str, default=None,
                        help="Model id for the second judge")
    parser.add_argument("--judge-disagree-threshold", type=int, default=2,
                        help="Judges disagree if pass/fail differs or score gap exceeds this")
    args = parser.parse_args()

    global SUBJECT_BACKEND, SUBJECT_MODEL, JUDGE_BACKEND, JUDGE_MODEL
    global JUDGE2_BACKEND, JUDGE2_MODEL, JUDGE_DISAGREE_THRESHOLD
    SUBJECT_BACKEND = args.subject_backend
    SUBJECT_MODEL = args.subject_model or ("opus" if SUBJECT_BACKEND == "claude" else "gpt-5.5")
    JUDGE_BACKEND = args.judge_backend
    JUDGE_MODEL = args.judge_model or ("opus" if JUDGE_BACKEND == "claude" else "gpt-5.5")
    JUDGE2_BACKEND = args.judge2_backend
    JUDGE2_MODEL = args.judge2_model
    JUDGE_DISAGREE_THRESHOLD = args.judge_disagree_threshold

    bin_for = {"claude": "claude", "copilot": "copilot"}
    backends = {SUBJECT_BACKEND, JUDGE_BACKEND}
    if JUDGE2_BACKEND:
        backends.add(JUDGE2_BACKEND)
    for backend in backends:
        if not shutil.which(bin_for[backend]):
            print(f"ERROR: {bin_for[backend]} CLI not found in PATH (needed for {backend} backend)")
            sys.exit(1)
    judges = f"{JUDGE_BACKEND}:{JUDGE_MODEL}"
    if JUDGE2_BACKEND:
        judges += f" + {JUDGE2_BACKEND}:{JUDGE2_MODEL} (dual, threshold={JUDGE_DISAGREE_THRESHOLD})"
    print(f"Subject: {SUBJECT_BACKEND}:{SUBJECT_MODEL}  |  Judge: {judges}")

    challenges = load_challenges(CHALLENGES_DIR)
    if args.challenges:
        challenges = [c for c in challenges if c.id in args.challenges]

    # Filter skill modes
    skill_modes = list(ALL_SKILL_MODES)
    if args.skill:
        skill_modes = [None]  # Always include baseline
        for s in args.skill:
            if s in ALL_SKILL_MODES and s is not None:
                skill_modes.append(s)

    total_combos = len(challenges) * len(skill_modes) * args.runs
    total_calls = total_combos * 2
    workers = max(1, args.workers)
    print(f"Running benchmark: {len(challenges)} challenges x {len(skill_modes)} modes x {args.runs} runs")
    print(f"Total calls: {total_calls} | Workers: {workers}")
    print()

    # Build list of all combos
    combos: list[tuple[Challenge, str | None, int]] = []
    for challenge in challenges:
        for skill in skill_modes:
            for run_idx in range(args.runs):
                combos.append((challenge, skill, run_idx))

    # Initialize results structure
    all_results: dict[str, dict[str, list[EvalResult]]] = {}
    for challenge in challenges:
        all_results[challenge.id] = {}
        for skill in skill_modes:
            all_results[challenge.id][label(skill)] = []

    def _run_combo(combo: tuple[Challenge, str | None, int]) -> tuple[str, str, int, EvalResult | None, str]:
        """Run a single combo; returns (cid, key, run_idx, result_or_None, status_msg)."""
        challenge, skill, run_idx = combo
        key = label(skill)
        try:
            result = run_one(challenge, skill)
            status = "PASS" if result.passed else "FAIL"
            return (challenge.id, key, run_idx, result, f"score={result.total_score} {status}")
        except Exception as e:
            return (challenge.id, key, run_idx, None, f"ERROR: {e}")

    start = time.time()
    completed = 0

    if workers == 1:
        # Sequential mode — preserve ordered output
        for combo in combos:
            completed += 1
            challenge, skill, run_idx = combo
            tag = f"[{completed}/{total_combos}]"
            print(f"  {tag} {challenge.id} + {label(skill)} (run {run_idx + 1})...", end=" ", flush=True)
            cid, key, _, result, msg = _run_combo(combo)
            if result:
                all_results[cid][key].append(result)
            print(msg)
    else:
        # Parallel mode
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_run_combo, c): c for c in combos}
            for future in as_completed(futures):
                completed += 1
                cid, key, run_idx, result, msg = future.result()
                if result:
                    all_results[cid][key].append(result)
                tag = f"[{completed}/{total_combos}]"
                print(f"  {tag} {cid} + {key} (run {run_idx + 1})... {msg}")

    elapsed = time.time() - start
    print(f"\nCompleted in {elapsed:.0f}s ({elapsed / 60:.1f}min)")

    # Build JSON data
    json_data = results_to_json(challenges, all_results, skill_modes)

    # Save if requested
    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
        print(f"\nResults saved to {args.save}")

    # Output
    if args.json:
        print(json.dumps(json_data, indent=2))
    else:
        print_element_grid(challenges, all_results, skill_modes)
        print_summary_table(challenges, all_results, skill_modes)

        # Comparison if requested
        if args.compare:
            saved = load_saved_results(Path(args.compare))
            print_comparison(json_data, saved)


if __name__ == "__main__":
    main()
