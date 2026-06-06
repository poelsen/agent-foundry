"""Evaluation runner for skill benchmarks.

Uses Claude-as-judge via the claude CLI to score responses against challenge rubrics.
Requires the claude CLI to be installed and available in PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from eval_rubric import (
    Challenge,
    DepthScore,
    ElementScore,
    EvalResult,
    OutcomeScore,
    score_response,
)
from skill_parser import parse_skill

JUDGE_MODEL = "opus"
SUBJECT_MODEL = "opus"


@dataclass(frozen=True)
class RunConfig:
    """Configuration for an evaluation run."""

    challenges: list[Challenge]
    skills_dir: Path
    runs_per_challenge: int = 3
    subject_model: str = SUBJECT_MODEL
    judge_model: str = JUDGE_MODEL


def _claude_cli(prompt: str, model: str = "opus") -> str:
    """Run a prompt through the claude CLI in non-interactive mode.

    Uses --output-format json for structured output and --permission-mode
    bypassPermissions for non-interactive / CI use.
    """
    claude_bin = shutil.which("claude")
    if not claude_bin:
        raise RuntimeError("claude CLI not found in PATH")

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
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {result.stderr.strip()}")

    # --output-format json wraps the response in a JSON object
    import json as _json
    try:
        data = _json.loads(result.stdout)
        if isinstance(data, dict) and "result" in data:
            return data["result"].strip()
        return result.stdout.strip()
    except _json.JSONDecodeError:
        return result.stdout.strip()


def _build_subject_prompt(
    challenge: Challenge,
    skill_content: str | None,
    length_match: int | None = None,
) -> str:
    """Build the prompt sent to the subject model.

    Args:
        challenge: The challenge to respond to.
        skill_content: Optional skill instructions to prepend.
        length_match: If set, instructs the model to write approximately this
            many words. Used for length-controlled baseline experiments to
            separate skill-technique effects from length effects.
    """
    parts: list[str] = []
    if skill_content:
        parts.append(f"<skill>\n{skill_content}\n</skill>\n")
    if length_match and not skill_content:
        parts.append(
            f"Write a thorough, detailed response of approximately {length_match} words. "
            "Cover all aspects of the problem in depth.\n"
        )
    parts.append(challenge.prompt)
    return "\n".join(parts)


def _build_judge_prompt(challenge: Challenge, response: str) -> str:
    """Build the prompt for the binary judge (present/absent scoring only)."""
    elements_desc = "\n".join(
        f"  - {eid}: {desc}" for eid, desc in challenge.rubric.required_elements.items()
    )
    anti_desc = "\n".join(
        f"  - {aid}: {desc}" for aid, desc in challenge.rubric.anti_patterns.items()
    )

    return f"""You are evaluating an AI response against a rubric. Score each element as present or absent.

## Challenge
{challenge.prompt}

## Response to evaluate
{response}

## Required elements (score each as present/absent with evidence)
{elements_desc}

## Anti-patterns (score each as present/absent with evidence)
{anti_desc}

Respond with ONLY valid JSON in this exact format:
{{
  "elements": {{
    "<element_id>": {{"present": true/false, "evidence": "brief quote or explanation"}},
    ...
  }},
  "anti_patterns": {{
    "<pattern_id>": {{"present": true/false, "evidence": "brief quote or explanation"}},
    ...
  }}
}}"""


def _build_depth_judge_prompt(challenge: Challenge, response: str) -> str:
    """Build a separate prompt for depth scoring (0-3 scale).

    Kept separate from binary judging to avoid halo effect — the depth judge
    doesn't see binary scores and makes independent quality assessments.
    """
    depth_desc = "\n".join(
        f"  - {did}: {desc}"
        for did, desc in challenge.rubric.depth_elements.items()
    )

    return f"""You are evaluating the DEPTH and QUALITY of an AI response. Do not judge presence/absence — only judge how deeply each topic is covered.

## Challenge
{challenge.prompt}

## Response to evaluate
{response}

## Depth elements (score each 0-3)
- 0 = absent or not addressed
- 1 = mentioned briefly without detail
- 2 = addressed with reasoning or explanation
- 3 = deep analysis with specific numbers, calculations, or concrete examples

{depth_desc}

Respond with ONLY valid JSON:
{{
  "depth": {{
    "<depth_id>": {{"score": 0, "evidence": "brief explanation"}},
    ...
  }}
}}"""


def _parse_judge_response(
    challenge: Challenge, judge_text: str
) -> tuple[list[ElementScore], list[ElementScore]]:
    """Parse the binary judge's JSON response into ElementScores."""
    text = _extract_json(judge_text)
    data = json.loads(text)

    element_scores: list[ElementScore] = []
    for eid in challenge.rubric.required_elements:
        entry = data.get("elements", {}).get(eid, {})
        element_scores.append(
            ElementScore(
                element_id=eid,
                present=entry.get("present", False),
                evidence=entry.get("evidence", ""),
            )
        )

    anti_scores: list[ElementScore] = []
    for aid in challenge.rubric.anti_patterns:
        entry = data.get("anti_patterns", {}).get(aid, {})
        anti_scores.append(
            ElementScore(
                element_id=aid,
                present=entry.get("present", False),
                evidence=entry.get("evidence", ""),
            )
        )

    return element_scores, anti_scores


def _parse_depth_response(
    challenge: Challenge, depth_text: str
) -> list[DepthScore]:
    """Parse the depth judge's JSON response into DepthScores."""
    text = _extract_json(depth_text)
    data = json.loads(text)

    depth_scores: list[DepthScore] = []
    for did in (challenge.rubric.depth_elements or {}):
        entry = data.get("depth", {}).get(did, {})
        depth_scores.append(
            DepthScore(
                element_id=did,
                score=min(3, max(0, entry.get("score", 0))),
                evidence=entry.get("evidence", ""),
            )
        )
    return depth_scores


def _build_outcome_judge_prompt(challenge: Challenge, response: str) -> str:
    """Build a separate prompt for outcome scoring (process-blind).

    Tests whether the response would change decisions, prevent losses, or earn
    expert endorsement — without reference to any specific analytical process.
    """
    outcome_desc = "\n".join(
        f"  - {oid}: {desc}"
        for oid, desc in challenge.rubric.outcome_elements.items()
    )

    return f"""You are evaluating whether an AI response produces REAL-WORLD VALUE — not whether it follows a process. Ignore methodology, structure, and formatting. Focus only on whether the content would actually help a decision-maker.

## Challenge
{challenge.prompt}

## Response to evaluate
{response}

## Outcome criteria (score each as met/not_met with evidence)
{outcome_desc}

Respond with ONLY valid JSON:
{{
  "outcomes": {{
    "<outcome_id>": {{"met": true/false, "evidence": "brief explanation"}},
    ...
  }}
}}"""


def _parse_outcome_response(
    challenge: Challenge, outcome_text: str
) -> list[OutcomeScore]:
    """Parse the outcome judge's JSON response into OutcomeScores."""
    text = _extract_json(outcome_text)
    data = json.loads(text)

    outcome_scores: list[OutcomeScore] = []
    for oid in (challenge.rubric.outcome_elements or {}):
        entry = data.get("outcomes", {}).get(oid, {})
        outcome_scores.append(
            OutcomeScore(
                element_id=oid,
                met=entry.get("met", False),
                evidence=entry.get("evidence", ""),
            )
        )
    return outcome_scores


def _extract_json(text: str) -> str:
    """Extract JSON from text, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    return text


def run_single_eval(
    challenge: Challenge,
    skill_content: str | None,
    config: RunConfig,
) -> EvalResult:
    """Run a single evaluation: subject responds, judge scores."""
    subject_prompt = _build_subject_prompt(challenge, skill_content)
    response = _claude_cli(subject_prompt, config.subject_model)

    judge_prompt = _build_judge_prompt(challenge, response)
    judge_text = _claude_cli(judge_prompt, config.judge_model)

    element_scores, anti_scores = _parse_judge_response(challenge, judge_text)

    # Separate depth judge call (avoids halo effect from binary scoring)
    depth_scores = []
    if challenge.rubric.depth_elements:
        depth_prompt = _build_depth_judge_prompt(challenge, response)
        depth_text = _claude_cli(depth_prompt, config.judge_model)
        depth_scores = _parse_depth_response(challenge, depth_text)

    # Separate outcome judge call (process-blind, tests decision quality)
    outcome_scores = []
    if challenge.rubric.outcome_elements:
        outcome_prompt = _build_outcome_judge_prompt(challenge, response)
        outcome_text = _claude_cli(outcome_prompt, config.judge_model)
        outcome_scores = _parse_outcome_response(challenge, outcome_text)

    return score_response(
        challenge,
        element_scores,
        anti_scores,
        skill_used=challenge.skill,
        raw_response=response,
        depth_scores=depth_scores,
        outcome_scores=outcome_scores,
    )


def run_challenge(
    challenge: Challenge,
    config: RunConfig,
) -> list[EvalResult]:
    """Run a challenge multiple times and return all results.

    Runs both with and without the skill for A/B comparison.
    """
    results: list[EvalResult] = []

    # Load skill content if specified
    skill_content: str | None = None
    if challenge.skill:
        skill_path = config.skills_dir / challenge.skill / "SKILL.md"
        if skill_path.exists():
            skill = parse_skill(skill_path)
            skill_content = skill.body

    for _ in range(config.runs_per_challenge):
        # Run with skill
        result_with = run_single_eval(challenge, skill_content, config)
        results.append(result_with)

        # Run baseline (without skill)
        baseline = run_single_eval(challenge, None, config)
        results.append(
            EvalResult(
                challenge_id=baseline.challenge_id,
                skill_used=None,
                element_scores=baseline.element_scores,
                anti_pattern_scores=baseline.anti_pattern_scores,
                total_score=baseline.total_score,
                passed=baseline.passed,
                raw_response=baseline.raw_response,
            )
        )

    return results


def run_evaluation(config: RunConfig) -> list[EvalResult]:
    """Run the full evaluation suite.

    Requires the claude CLI to be installed and available in PATH.

    Returns list of all EvalResults across all challenges and runs.
    """
    if not shutil.which("claude"):
        raise RuntimeError("claude CLI not found in PATH")

    all_results: list[EvalResult] = []

    for challenge in config.challenges:
        results = run_challenge(challenge, config)
        all_results.extend(results)

    return all_results
