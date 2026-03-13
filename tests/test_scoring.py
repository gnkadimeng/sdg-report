"""
Unit tests for deterministic scoring logic.

These tests do NOT require Ollama or any external services.
They validate the scoring rules against the documented specification.

Run with: pytest tests/test_scoring.py -v
"""

import pytest
from app.nodes.score_evidence import (
    DOCUMENTED_MAX_SCORE,
    MATURITY_SCORES,
    MODERATE_MAX,
    TAG_BONUSES,
    WEAK_MAX,
    _compute_score,
)
from app.schemas.state import EvidenceRecord


def _make_record(**kwargs) -> EvidenceRecord:
    """Create a minimal valid EvidenceRecord for testing."""
    defaults = {
        "evidence_id": "test-001",
        "company": "TestCo",
        "report_name": "Test Report",
        "report_year": 2023,
        "page_number": 1,
        "section_heading": "Test Section",
        "evidence_text": "Some evidence text.",
        "evidence_summary": "A test summary.",
        "candidate_sdgs": ["SDG 13"],
        "evidence_tags": [],
        "implementation_stage": "mention_only",
        "quantitative_support": False,
        "oversight_support": False,
        "confidence": 0.8,
        "rationale": "Test rationale.",
        "validation_status": "valid",
        "validation_errors": [],
        "computed_strength": "",
        "computed_score": 0,
    }
    defaults.update(kwargs)
    return defaults  # type: ignore[return-value]


class TestMatureScores:
    def test_mention_only_base(self):
        record = _make_record(implementation_stage="mention_only")
        score, strength = _compute_score(record)
        assert score == 1
        assert strength == "weak"

    def test_planned_action_base(self):
        record = _make_record(implementation_stage="planned_action")
        score, strength = _compute_score(record)
        assert score == 2
        assert strength == "weak"

    def test_implementation_in_progress_base(self):
        record = _make_record(implementation_stage="implementation_in_progress")
        score, strength = _compute_score(record)
        assert score == 3
        assert strength == "moderate"

    def test_implemented_with_measurable_base(self):
        record = _make_record(
            implementation_stage="implemented_with_measurable_evidence"
        )
        score, strength = _compute_score(record)
        assert score == 4
        assert strength == "moderate"


class TestTagBonuses:
    def test_policy_bonus(self):
        record = _make_record(
            implementation_stage="mention_only", evidence_tags=["policy"]
        )
        score, _ = _compute_score(record)
        assert score == 1 + 1  # base + policy

    def test_measured_outcome_bonus(self):
        record = _make_record(
            implementation_stage="mention_only", evidence_tags=["measured_outcome"]
        )
        score, _ = _compute_score(record)
        assert score == 1 + 2  # base + measured_outcome

    def test_kpi_bonus(self):
        record = _make_record(
            implementation_stage="planned_action", evidence_tags=["kpi"]
        )
        score, _ = _compute_score(record)
        assert score == 2 + 1  # base + kpi

    def test_aspiration_no_bonus(self):
        record = _make_record(
            implementation_stage="mention_only", evidence_tags=["aspiration"]
        )
        score, _ = _compute_score(record)
        assert score == 1  # no bonus for aspiration

    def test_governance_no_bonus(self):
        record = _make_record(
            implementation_stage="mention_only", evidence_tags=["governance"]
        )
        score, _ = _compute_score(record)
        assert score == 1  # no bonus for governance alone

    def test_multiple_tag_bonuses(self):
        record = _make_record(
            implementation_stage="planned_action",
            evidence_tags=["policy", "target", "kpi"],
        )
        score, _ = _compute_score(record)
        # 2 (planned) + 1 (policy) + 1 (target) + 1 (kpi) = 5
        assert score == 5
        assert _compute_score(record)[1] == "moderate"


class TestSupportBonuses:
    def test_quantitative_support_bonus(self):
        record = _make_record(
            implementation_stage="mention_only", quantitative_support=True
        )
        score, _ = _compute_score(record)
        assert score == 2  # 1 + 1

    def test_oversight_support_bonus(self):
        record = _make_record(
            implementation_stage="mention_only", oversight_support=True
        )
        score, _ = _compute_score(record)
        assert score == 2  # 1 + 1

    def test_both_support_bonuses(self):
        record = _make_record(
            implementation_stage="mention_only",
            quantitative_support=True,
            oversight_support=True,
        )
        score, _ = _compute_score(record)
        assert score == 3  # 1 + 1 + 1 → moderate


class TestStrengthMapping:
    def test_score_1_is_weak(self):
        record = _make_record(implementation_stage="mention_only")
        _, strength = _compute_score(record)
        assert strength == "weak"

    def test_score_2_is_weak(self):
        record = _make_record(
            implementation_stage="planned_action"
        )
        score, strength = _compute_score(record)
        assert score == 2
        assert strength == "weak"

    def test_score_3_is_moderate(self):
        record = _make_record(implementation_stage="implementation_in_progress")
        _, strength = _compute_score(record)
        assert strength == "moderate"

    def test_score_6_is_strong(self):
        # 4 (implemented) + 1 (kpi) + 1 (quantitative) = 6
        record = _make_record(
            implementation_stage="implemented_with_measurable_evidence",
            evidence_tags=["kpi"],
            quantitative_support=True,
        )
        score, strength = _compute_score(record)
        assert score == 6
        assert strength == "strong"

    def test_maximum_possible_score(self):
        # Max: 4 + 1+1+1+1+2 + 1+1 = 12
        record = _make_record(
            implementation_stage="implemented_with_measurable_evidence",
            evidence_tags=["policy", "initiative", "target", "kpi", "measured_outcome"],
            quantitative_support=True,
            oversight_support=True,
        )
        score, strength = _compute_score(record)
        assert score == DOCUMENTED_MAX_SCORE
        assert strength == "strong"

    def test_score_capped_at_max(self):
        """Score cannot exceed DOCUMENTED_MAX_SCORE even with extra tags."""
        record = _make_record(
            implementation_stage="implemented_with_measurable_evidence",
            evidence_tags=[
                "policy", "initiative", "target", "kpi",
                "measured_outcome", "governance", "aspiration"
            ],
            quantitative_support=True,
            oversight_support=True,
        )
        score, _ = _compute_score(record)
        assert score <= DOCUMENTED_MAX_SCORE


class TestDocumentedConstants:
    """Verify the scoring constants match the spec."""

    def test_maturity_values(self):
        assert MATURITY_SCORES["mention_only"] == 1
        assert MATURITY_SCORES["planned_action"] == 2
        assert MATURITY_SCORES["implementation_in_progress"] == 3
        assert MATURITY_SCORES["implemented_with_measurable_evidence"] == 4

    def test_tag_bonus_values(self):
        assert TAG_BONUSES["policy"] == 1
        assert TAG_BONUSES["initiative"] == 1
        assert TAG_BONUSES["target"] == 1
        assert TAG_BONUSES["kpi"] == 1
        assert TAG_BONUSES["measured_outcome"] == 2

    def test_strength_thresholds(self):
        assert WEAK_MAX == 2
        assert MODERATE_MAX == 5

    def test_documented_max_score(self):
        assert DOCUMENTED_MAX_SCORE == 12
