"""
Unit tests for deterministic validation logic.

These tests do NOT require Ollama or any external services.
They validate every validation rule in validate_evidence_node.

Run with: pytest tests/test_validation.py -v
"""

import pytest
from app.nodes.validate_evidence import (
    VALID_EVIDENCE_TAGS,
    VALID_IMPLEMENTATION_STAGES,
    _validate_record,
)
from app.schemas.state import EvidenceRecord


def _make_valid_record(**kwargs) -> EvidenceRecord:
    """Create a minimal valid EvidenceRecord that should pass all checks."""
    defaults = {
        "evidence_id": "test-001",
        "company": "TestCo",
        "report_name": "Test Report",
        "report_year": 2023,
        "page_number": 5,
        "section_heading": "Climate",
        "evidence_text": "We reduced emissions by 20% in 2023.",
        "evidence_summary": "A 20% emission reduction.",
        "candidate_sdgs": ["SDG 13"],
        "evidence_tags": ["measured_outcome"],
        "implementation_stage": "implemented_with_measurable_evidence",
        "quantitative_support": True,   # required for measured_outcome
        "oversight_support": False,
        "confidence": 0.9,
        "rationale": "Clear numeric reduction reported.",
        "validation_status": "pending",
        "validation_errors": [],
        "computed_strength": "",
        "computed_score": 0,
    }
    defaults.update(kwargs)
    return defaults  # type: ignore[return-value]


class TestValidRecord:
    def test_valid_record_passes(self):
        record = _make_valid_record()
        errors = _validate_record(record)
        assert errors == []

    def test_valid_record_with_policy_tag(self):
        record = _make_valid_record(
            evidence_tags=["policy"],
            implementation_stage="planned_action",
            quantitative_support=False,
        )
        errors = _validate_record(record)
        assert errors == []


class TestRule1PageNumber:
    def test_missing_page_number(self):
        record = _make_valid_record(page_number=None)
        errors = _validate_record(record)
        assert any("page_number" in e for e in errors)

    def test_zero_page_number(self):
        record = _make_valid_record(page_number=0)
        errors = _validate_record(record)
        assert any("page_number" in e for e in errors)

    def test_negative_page_number(self):
        record = _make_valid_record(page_number=-1)
        errors = _validate_record(record)
        assert any("page_number" in e for e in errors)

    def test_valid_page_number(self):
        record = _make_valid_record(page_number=1)
        errors = _validate_record(record)
        assert not any("page_number" in e for e in errors)


class TestRule2EvidenceText:
    def test_empty_evidence_text(self):
        record = _make_valid_record(evidence_text="")
        errors = _validate_record(record)
        assert any("evidence_text" in e for e in errors)

    def test_whitespace_only_evidence_text(self):
        record = _make_valid_record(evidence_text="   ")
        errors = _validate_record(record)
        assert any("evidence_text" in e for e in errors)

    def test_valid_evidence_text(self):
        record = _make_valid_record(evidence_text="We reduced emissions.")
        errors = _validate_record(record)
        assert not any("evidence_text" in e for e in errors)


class TestRule3CandidateSDGs:
    def test_empty_candidate_sdgs(self):
        record = _make_valid_record(candidate_sdgs=[])
        errors = _validate_record(record)
        assert any("candidate_sdgs" in e for e in errors)

    def test_invalid_sdg_format(self):
        record = _make_valid_record(candidate_sdgs=["Goal 13", "Climate"])
        errors = _validate_record(record)
        assert any("invalid SDG" in e for e in errors)

    def test_valid_sdg_format(self):
        record = _make_valid_record(candidate_sdgs=["SDG 1"])
        errors = _validate_record(record)
        assert not any("candidate_sdgs" in e or "SDG" in e for e in errors)

    def test_all_valid_sdgs(self):
        for i in range(1, 18):
            record = _make_valid_record(candidate_sdgs=[f"SDG {i}"])
            errors = _validate_record(record)
            assert not any("invalid SDG" in e for e in errors), f"SDG {i} rejected"


class TestRule4ImplementationStage:
    def test_invalid_stage(self):
        record = _make_valid_record(implementation_stage="active")
        errors = _validate_record(record)
        assert any("implementation_stage" in e for e in errors)

    def test_all_valid_stages(self):
        for stage in VALID_IMPLEMENTATION_STAGES:
            record = _make_valid_record(
                implementation_stage=stage,
                quantitative_support=True,  # needed for implemented_with_measurable
                evidence_tags=["measured_outcome"],
            )
            errors = [e for e in _validate_record(record) if "implementation_stage" in e]
            assert not errors, f"Stage '{stage}' wrongly rejected"


class TestRule5EvidenceTags:
    def test_invalid_tag(self):
        record = _make_valid_record(evidence_tags=["action"])
        errors = _validate_record(record)
        assert any("evidence_tags" in e for e in errors)

    def test_all_valid_tags(self):
        for tag in VALID_EVIDENCE_TAGS - {"measured_outcome", "governance"}:
            record = _make_valid_record(evidence_tags=[tag])
            errors = [e for e in _validate_record(record) if "evidence_tags" in e]
            assert not errors, f"Tag '{tag}' wrongly rejected"

    def test_mixed_valid_invalid_tags(self):
        record = _make_valid_record(evidence_tags=["policy", "action_item"])
        errors = _validate_record(record)
        assert any("evidence_tags" in e for e in errors)


class TestRule6MeasuredOutcomeRequiresQuantitative:
    def test_measured_outcome_without_quant_rejected(self):
        record = _make_valid_record(
            evidence_tags=["measured_outcome"],
            quantitative_support=False,
        )
        errors = _validate_record(record)
        assert any("measured_outcome" in e for e in errors)

    def test_measured_outcome_with_quant_passes(self):
        record = _make_valid_record(
            evidence_tags=["measured_outcome"],
            quantitative_support=True,
        )
        errors = _validate_record(record)
        assert not any("measured_outcome" in e for e in errors)


class TestRule7GovernanceRequiresOversight:
    def test_governance_without_oversight_rejected(self):
        record = _make_valid_record(
            evidence_tags=["governance"],
            oversight_support=False,
            implementation_stage="planned_action",
            quantitative_support=False,
        )
        errors = _validate_record(record)
        assert any("governance" in e for e in errors)

    def test_governance_with_oversight_passes(self):
        record = _make_valid_record(
            evidence_tags=["governance"],
            oversight_support=True,
            implementation_stage="planned_action",
            quantitative_support=False,
        )
        errors = _validate_record(record)
        assert not any("governance" in e for e in errors)


class TestRule8ImplementedStageRequiresQuantitative:
    def test_implemented_stage_without_quant_rejected(self):
        record = _make_valid_record(
            implementation_stage="implemented_with_measurable_evidence",
            quantitative_support=False,
            evidence_tags=["measured_outcome"],  # will also fail rule 6
        )
        errors = _validate_record(record)
        assert any("implemented_with_measurable_evidence" in e for e in errors)

    def test_implemented_stage_with_quant_passes(self):
        record = _make_valid_record(
            implementation_stage="implemented_with_measurable_evidence",
            quantitative_support=True,
            evidence_tags=["measured_outcome"],
        )
        errors = _validate_record(record)
        assert not any("implemented_with_measurable_evidence" in e for e in errors)


class TestMultipleErrors:
    def test_multiple_violations_reported(self):
        record = _make_valid_record(
            page_number=0,
            evidence_text="",
            candidate_sdgs=[],
        )
        errors = _validate_record(record)
        assert len(errors) >= 3

    def test_clean_record_zero_errors(self):
        record = _make_valid_record()
        errors = _validate_record(record)
        assert len(errors) == 0
