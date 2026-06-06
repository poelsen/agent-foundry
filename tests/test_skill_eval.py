"""Tests for eval_runner.py and eval_report.py.

Tier 2: Challenge structure validation (always runs).
Tier 3: CLI-based evaluation (requires --run-eval and claude CLI in PATH).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from eval_report import json_report, markdown_report, terminal_report
from eval_rubric import (
    Challenge,
    ElementScore,
    EvalResult,
    Rubric,
    load_challenges,
)
from eval_runner import (
    RunConfig,
    _build_judge_prompt,
    _build_subject_prompt,
    _parse_judge_response,
)

REPO_ROOT = Path(__file__).parent.parent
CHALLENGES_DIR = Path(__file__).parent / "challenges"
SKILLS_DIR = REPO_ROOT / "cli" / "claude" / "skills"


# ── Tier 2: Challenge structure validation ──


class TestChallengeStructure:
    """Validate challenge YAML files have valid rubrics."""

    def test_all_challenges_load(self):
        challenges = load_challenges(CHALLENGES_DIR)
        assert len(challenges) >= 30

    def test_all_challenges_have_required_fields(self):
        for c in load_challenges(CHALLENGES_DIR):
            assert c.id, "Challenge missing id"
            assert c.name, f"Challenge {c.id} missing name"
            assert c.category, f"Challenge {c.id} missing category"
            assert c.prompt, f"Challenge {c.id} missing prompt"
            assert c.rubric.required_elements, f"Challenge {c.id} has no required elements"
            assert c.rubric.passing_score > 0, f"Challenge {c.id} has non-positive passing score"

    def test_passing_score_achievable(self):
        for c in load_challenges(CHALLENGES_DIR):
            max_score = len(c.rubric.required_elements)
            assert c.rubric.passing_score <= max_score, (
                f"Challenge {c.id}: passing_score {c.rubric.passing_score} > "
                f"max possible {max_score}"
            )

    def test_unique_challenge_ids(self):
        challenges = load_challenges(CHALLENGES_DIR)
        ids = [c.id for c in challenges]
        assert len(ids) == len(set(ids)), f"Duplicate challenge IDs: {ids}"

    def test_skill_targets_exist(self):
        for c in load_challenges(CHALLENGES_DIR):
            if c.skill:
                skill_dir = SKILLS_DIR / c.skill
                assert skill_dir.is_dir(), (
                    f"Challenge {c.id} targets skill '{c.skill}' which doesn't exist"
                )


# ── Prompt building tests ──


class TestPromptBuilding:
    """Tests for subject and judge prompt construction."""

    @pytest.fixture
    def sample_challenge(self) -> Challenge:
        return Challenge(
            id="test-001",
            name="Test",
            category="test",
            prompt="Build a widget.",
            rubric=Rubric(
                required_elements={"thinks": "Shows thinking", "asks": "Asks questions"},
                anti_patterns={"rushes": "Jumps to code"},
                passing_score=1,
            ),
        )

    def test_subject_prompt_without_skill(self, sample_challenge: Challenge):
        prompt = _build_subject_prompt(sample_challenge, None)
        assert "Build a widget." in prompt
        assert "<skill>" not in prompt

    def test_subject_prompt_with_skill(self, sample_challenge: Challenge):
        prompt = _build_subject_prompt(sample_challenge, "Think before acting.")
        assert "<skill>" in prompt
        assert "Think before acting." in prompt
        assert "Build a widget." in prompt

    def test_judge_prompt_contains_rubric(self, sample_challenge: Challenge):
        prompt = _build_judge_prompt(sample_challenge, "I built the widget.")
        assert "I built the widget." in prompt
        assert "thinks" in prompt
        assert "asks" in prompt
        assert "rushes" in prompt
        assert "JSON" in prompt


# ── Judge response parsing ──


class TestJudgeParsing:
    """Tests for parsing judge model responses."""

    @pytest.fixture
    def sample_challenge(self) -> Challenge:
        return Challenge(
            id="test-001",
            name="Test",
            category="test",
            prompt="Do something.",
            rubric=Rubric(
                required_elements={"elem_a": "Does A", "elem_b": "Does B"},
                anti_patterns={"bad": "Bad thing"},
                passing_score=1,
            ),
        )

    def test_parse_clean_json(self, sample_challenge: Challenge):
        judge_text = json.dumps({
            "elements": {
                "elem_a": {"present": True, "evidence": "Found it"},
                "elem_b": {"present": False, "evidence": "Missing"},
            },
            "anti_patterns": {
                "bad": {"present": False, "evidence": "Not found"},
            },
        })

        elements, anti = _parse_judge_response(sample_challenge, judge_text)

        assert len(elements) == 2
        assert elements[0].present is True
        assert elements[0].evidence == "Found it"
        assert elements[1].present is False
        assert len(anti) == 1
        assert anti[0].present is False

    def test_parse_json_in_code_block(self, sample_challenge: Challenge):
        judge_text = '```json\n{"elements": {"elem_a": {"present": true, "evidence": ""}, "elem_b": {"present": true, "evidence": ""}}, "anti_patterns": {"bad": {"present": false, "evidence": ""}}}\n```'

        elements, _anti = _parse_judge_response(sample_challenge, judge_text)

        assert len(elements) == 2
        assert all(e.present for e in elements)

    def test_missing_element_defaults_false(self, sample_challenge: Challenge):
        judge_text = json.dumps({
            "elements": {"elem_a": {"present": True, "evidence": "yes"}},
            "anti_patterns": {},
        })

        elements, _anti = _parse_judge_response(sample_challenge, judge_text)

        assert elements[0].present is True
        assert elements[1].present is False  # elem_b missing → defaults False


# ── Report generation ──


class TestReports:
    """Tests for report generation."""

    @pytest.fixture
    def sample_results(self) -> list[EvalResult]:
        return [
            EvalResult(
                challenge_id="test-001",
                skill_used="megamind",
                element_scores=(
                    ElementScore("a", True, "found"),
                    ElementScore("b", True, "found"),
                ),
                anti_pattern_scores=(ElementScore("bad", False, ""),),
                total_score=2,
                passed=True,
            ),
            EvalResult(
                challenge_id="test-001",
                skill_used=None,
                element_scores=(
                    ElementScore("a", True, "found"),
                    ElementScore("b", False, "missing"),
                ),
                anti_pattern_scores=(ElementScore("bad", True, "jumped to code"),),
                total_score=0,
                passed=False,
            ),
        ]

    def test_terminal_report(self, sample_results: list[EvalResult]):
        report = terminal_report(sample_results)
        assert "test-001" in report
        assert "megamind" in report
        assert "Baseline" in report
        assert "Delta" in report

    def test_terminal_report_empty(self):
        assert "No results" in terminal_report([])

    def test_json_report_valid(self, sample_results: list[EvalResult]):
        report = json_report(sample_results)
        data = json.loads(report)
        assert "results" in data
        assert "summary" in data
        assert len(data["results"]) == 2
        assert data["summary"]["total_results"] == 2

    def test_markdown_report(self, sample_results: list[EvalResult]):
        report = markdown_report(sample_results)
        assert "# Skill Evaluation Report" in report
        assert "test-001" in report
        assert "megamind" in report
        assert "PASS" in report
        assert "FAIL" in report

    def test_markdown_report_empty(self):
        report = markdown_report([])
        assert "No results" in report


# ── Tier 3: CLI-based evaluation (gated) ──


@pytest.mark.eval
class TestCLIEvaluation:
    """CLI-based evaluation tests. Requires --run-eval and claude CLI in PATH."""

    def test_single_challenge_evaluation(self):
        """Run a single challenge and verify scoring works end-to-end."""
        from eval_runner import run_evaluation

        challenges = load_challenges(CHALLENGES_DIR)
        # Pick the simplest challenge
        scope = next((c for c in challenges if c.id == "scope-001"), challenges[0])

        config = RunConfig(
            challenges=[scope],
            skills_dir=SKILLS_DIR,
            runs_per_challenge=1,
        )

        results = run_evaluation(config)
        assert len(results) == 2  # 1 with skill + 1 baseline
        assert all(isinstance(r, EvalResult) for r in results)
        assert results[0].skill_used is not None
        assert results[1].skill_used is None

    def test_skill_improves_score(self):
        """Run multiple challenges and check if skills improve scores on average."""
        from eval_runner import run_evaluation

        challenges = load_challenges(CHALLENGES_DIR)

        config = RunConfig(
            challenges=challenges[:2],
            skills_dir=SKILLS_DIR,
            runs_per_challenge=1,
        )

        results = run_evaluation(config)
        with_skill = [r for r in results if r.skill_used is not None]
        baseline = [r for r in results if r.skill_used is None]

        # Report regardless of outcome
        report = terminal_report(results)
        print(report)

        # We just verify it ran without error — improvement is aspirational
        assert len(with_skill) > 0
        assert len(baseline) > 0
