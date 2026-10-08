"""Tests for eval_rubric.py — challenge loading and scoring."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from eval_rubric import (
    Challenge,
    ElementScore,
    EvalResult,
    Rubric,
    load_challenge,
    load_challenges,
    score_response,
)

CHALLENGES_DIR = Path(__file__).parent / "challenges"


# ── Challenge loading ──


class TestLoadChallenge:
    """Tests for loading challenge YAML files."""

    def test_load_valid_challenge(self):
        path = CHALLENGES_DIR / "arch-001.yaml"
        if not path.exists():
            pytest.skip("Challenge file not found")

        challenge = load_challenge(path)

        assert challenge.id == "arch-001"
        assert challenge.name == "Architecture Decision Under Ambiguity"
        assert challenge.category == "reasoning_depth"
        assert "real-time notifications" in challenge.prompt
        assert len(challenge.rubric.required_elements) >= 3
        assert challenge.rubric.passing_score > 0

    def test_load_all_challenges(self):
        challenges = load_challenges(CHALLENGES_DIR)
        assert len(challenges) == 110
        ids = {c.id for c in challenges}
        assert "arch-001" in ids
        assert "creative-001" in ids
        assert "adversarial-001" in ids

    def test_challenge_has_skill(self):
        challenge = load_challenge(CHALLENGES_DIR / "scope-001.yaml")
        assert challenge.skill == "megamind-deep"

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_challenge(tmp_path / "nonexistent.yaml")

    def test_missing_required_field_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("id: test\nname: test\n")

        with pytest.raises(ValueError, match="Missing required field"):
            load_challenge(bad)

    def test_missing_rubric_field_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "id: test\nname: test\ncategory: test\nprompt: test\n"
            "rubric:\n  anti_patterns: {}\n"
        )

        with pytest.raises(ValueError, match="Missing required rubric field"):
            load_challenge(bad)

    def test_nonexistent_directory(self, tmp_path):
        challenges = load_challenges(tmp_path / "nope")
        assert challenges == []

    def test_invalid_yaml_type_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("- just\n- a\n- list\n")

        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_challenge(bad)


# ── Scoring ──


class TestScoring:
    """Tests for response scoring logic."""

    @pytest.fixture
    def sample_challenge(self) -> Challenge:
        return Challenge(
            id="test-001",
            name="Test Challenge",
            category="test",
            prompt="Do the thing",
            rubric=Rubric(
                required_elements={
                    "element_a": "Does A",
                    "element_b": "Does B",
                    "element_c": "Does C",
                },
                anti_patterns={
                    "bad_thing": "Does bad thing",
                },
                passing_score=2,
            ),
        )

    def test_perfect_score(self, sample_challenge: Challenge):
        elements = [
            ElementScore("element_a", present=True),
            ElementScore("element_b", present=True),
            ElementScore("element_c", present=True),
        ]
        anti = [ElementScore("bad_thing", present=False)]

        result = score_response(sample_challenge, elements, anti)

        assert result.total_score == 3
        assert result.passed is True

    def test_failing_score(self, sample_challenge: Challenge):
        elements = [
            ElementScore("element_a", present=True),
            ElementScore("element_b", present=False),
            ElementScore("element_c", present=False),
        ]
        anti = [ElementScore("bad_thing", present=False)]

        result = score_response(sample_challenge, elements, anti)

        assert result.total_score == 1
        assert result.passed is False

    def test_anti_patterns_subtract(self, sample_challenge: Challenge):
        elements = [
            ElementScore("element_a", present=True),
            ElementScore("element_b", present=True),
            ElementScore("element_c", present=False),
        ]
        anti = [ElementScore("bad_thing", present=True)]

        result = score_response(sample_challenge, elements, anti)

        assert result.total_score == 0  # 2 - 2 (anti-patterns cost -2 each)
        assert result.passed is False

    def test_skill_recorded(self, sample_challenge: Challenge):
        result = score_response(sample_challenge, [], [], skill_used="megamind")
        assert result.skill_used == "megamind"

    def test_raw_response_recorded(self, sample_challenge: Challenge):
        result = score_response(
            sample_challenge, [], [], raw_response="Full model output"
        )
        assert result.raw_response == "Full model output"

    def test_challenge_id_recorded(self, sample_challenge: Challenge):
        result = score_response(sample_challenge, [], [])
        assert result.challenge_id == "test-001"

    def test_evidence_in_element_score(self):
        score = ElementScore("test", present=True, evidence="Found in paragraph 2")
        assert score.evidence == "Found in paragraph 2"


# ── Data structure tests ──


class TestDataStructures:
    """Tests for frozen dataclass invariants."""

    def test_rubric_frozen(self):
        rubric = Rubric({"a": "b"}, {}, 3)
        with pytest.raises(AttributeError):
            rubric.passing_score = 5  # type: ignore[misc]

    def test_challenge_frozen(self):
        challenge = Challenge("id", "name", "cat", "prompt", Rubric({}, {}, 1))
        with pytest.raises(AttributeError):
            challenge.id = "new"  # type: ignore[misc]

    def test_eval_result_frozen(self):
        result = EvalResult("id", None, (), (), 0, False)
        with pytest.raises(AttributeError):
            result.total_score = 99  # type: ignore[misc]
