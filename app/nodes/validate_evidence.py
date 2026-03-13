"""
LangGraph node: validate_evidence

All validation is deterministic Python — no LLM judgment.

Validation rules:
    1. page_number must be present and > 0
    2. evidence_text must be non-empty
    3. candidate_sdgs must be a non-empty list
    4. implementation_stage must be one of VALID_IMPLEMENTATION_STAGES
    5. all evidence_tags must be from VALID_EVIDENCE_TAGS
    6. "measured_outcome" tag requires quantitative_support == True
    7. "governance" tag requires oversight_support == True
    8. "implemented_with_measurable_evidence" stage requires
       quantitative_support == True

Items failing any rule are moved to rejected_evidence with error details.
Items passing all rules get validation_status = "valid".

Returns: validated_evidence, rejected_evidence, errors
"""

from __future__ import annotations

from typing import List

from app.schemas.state import EvidenceRecord, PipelineState
from app.utils.logger import get_logger

logger = get_logger(__name__)

VALID_IMPLEMENTATION_STAGES = {
    "mention_only",
    "planned_action",
    "implementation_in_progress",
    "implemented_with_measurable_evidence",
}

VALID_EVIDENCE_TAGS = {
    "aspiration",
    "policy",
    "initiative",
    "target",
    "kpi",
    "governance",
    "measured_outcome",
}

VALID_SDG_PATTERN = {f"SDG {i}" for i in range(1, 18)}


def _validate_record(record: EvidenceRecord) -> List[str]:
    """
    Run all validation checks against a single EvidenceRecord.

    Returns a list of error strings. Empty list = valid.
    """
    errors: List[str] = []

    # Rule 1: page_number
    page_number = record.get("page_number")
    if not page_number or not isinstance(page_number, int) or page_number < 1:
        errors.append("page_number is missing or invalid")

    # Rule 2: evidence_text
    evidence_text = record.get("evidence_text", "").strip()
    if not evidence_text:
        errors.append("evidence_text is empty")

    # Rule 3: candidate_sdgs
    candidate_sdgs = record.get("candidate_sdgs", [])
    if not isinstance(candidate_sdgs, list) or len(candidate_sdgs) == 0:
        errors.append("candidate_sdgs is empty")
    else:
        invalid_sdgs = [s for s in candidate_sdgs if s not in VALID_SDG_PATTERN]
        if invalid_sdgs:
            errors.append(f"invalid SDG identifiers: {invalid_sdgs}")

    # Rule 4: implementation_stage
    stage = record.get("implementation_stage", "")
    if stage not in VALID_IMPLEMENTATION_STAGES:
        errors.append(
            f"implementation_stage '{stage}' is not one of {sorted(VALID_IMPLEMENTATION_STAGES)}"
        )

    # Rule 5: evidence_tags
    tags = record.get("evidence_tags", [])
    if not isinstance(tags, list):
        errors.append("evidence_tags is not a list")
    else:
        invalid_tags = [t for t in tags if t not in VALID_EVIDENCE_TAGS]
        if invalid_tags:
            errors.append(f"invalid evidence_tags: {invalid_tags}")

    # Rule 6: measured_outcome requires quantitative_support
    if "measured_outcome" in (tags or []):
        if not record.get("quantitative_support", False):
            errors.append(
                "'measured_outcome' tag requires quantitative_support == True "
                "(no numeric or metric evidence found by model)"
            )

    # Rule 7: governance tag requires oversight_support
    if "governance" in (tags or []):
        if not record.get("oversight_support", False):
            errors.append(
                "'governance' tag requires oversight_support == True "
                "(no board/committee/executive oversight found by model)"
            )

    # Rule 8: implemented_with_measurable_evidence requires quantitative_support
    if stage == "implemented_with_measurable_evidence":
        if not record.get("quantitative_support", False):
            errors.append(
                "'implemented_with_measurable_evidence' stage requires "
                "quantitative_support == True"
            )

    return errors


def validate_evidence_node(state: PipelineState) -> dict:
    """
    Validate all extracted evidence items deterministically.

    Returns partial state update:
        validated_evidence: List[EvidenceRecord] (status = "valid")
        rejected_evidence:  List[EvidenceRecord] (status = "rejected")
        errors: accumulated errors list
    """
    existing_errors = list(state.get("errors", []))
    extracted = state.get("extracted_evidence", [])

    if not extracted:
        logger.warning("validate_evidence: no extracted evidence to validate.")
        return {
            "validated_evidence": [],
            "rejected_evidence": [],
            "errors": existing_errors,
        }

    logger.info(
        "Node: validate_evidence — validating %d evidence items.", len(extracted)
    )

    validated: List[EvidenceRecord] = []
    rejected: List[EvidenceRecord] = []

    for record in extracted:
        validation_errors = _validate_record(record)
        if validation_errors:
            updated = {
                **record,
                "validation_status": "rejected",
                "validation_errors": validation_errors,
            }
            rejected.append(updated)
            logger.debug(
                "Rejected evidence %s (page %d): %s",
                record.get("evidence_id", "?"),
                record.get("page_number", 0),
                "; ".join(validation_errors),
            )
        else:
            updated = {
                **record,
                "validation_status": "valid",
                "validation_errors": [],
            }
            validated.append(updated)

    logger.info(
        "validate_evidence: %d valid, %d rejected (from %d total).",
        len(validated),
        len(rejected),
        len(extracted),
    )

    return {
        "validated_evidence": validated,
        "rejected_evidence": rejected,
        "errors": existing_errors,
    }
