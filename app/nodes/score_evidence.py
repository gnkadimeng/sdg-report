"""
LangGraph node: score_evidence

All scoring is deterministic. The LLM does NOT assign strength labels.

Scoring formula
===============
1. Action maturity (base score):
       mention_only                        = 1
       planned_action                      = 2
       implementation_in_progress          = 3
       implemented_with_measurable_evidence = 4

2. Evidence tag bonuses (additive):
       policy          +1
       initiative      +1
       target          +1
       kpi             +1
       measured_outcome +2
       (aspiration, governance → no bonus)

3. Support modifiers:
       quantitative_support == True  +1
       oversight_support == True     +1

Raw score = base + tag_bonus + support_bonus
Documented maximum = 4 + 2 + 1 + 1 + 1 + 1 + 1 + 1 = 12
  (base 4 + measured_outcome 2 + policy 1 + initiative 1 + target 1 + kpi 1
   + quantitative 1 + oversight 1)

Strength mapping:
       score ∈ [1, 2]  → "weak"
       score ∈ [3, 5]  → "moderate"
       score ≥ 6       → "strong"

Only validated evidence is scored.
"""

from __future__ import annotations

from typing import List

from app.schemas.state import EvidenceRecord, PipelineState
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Scoring tables (deterministic)
# ---------------------------------------------------------------------------

MATURITY_SCORES = {
    "mention_only": 1,
    "planned_action": 2,
    "implementation_in_progress": 3,
    "implemented_with_measurable_evidence": 4,
}

TAG_BONUSES = {
    "policy": 1,
    "initiative": 1,
    "target": 1,
    "kpi": 1,
    "measured_outcome": 2,
    # "aspiration" and "governance" → 0
}

DOCUMENTED_MAX_SCORE = 12

# Strength thresholds
WEAK_MAX = 2
MODERATE_MAX = 5
# strong = MODERATE_MAX + 1 and above


def _compute_score(record: EvidenceRecord) -> tuple[int, str]:
    """
    Compute the raw score and strength label for a validated evidence record.

    Returns:
        (score, strength) where strength is "weak" | "moderate" | "strong"
    """
    # Base score from action maturity
    stage = record.get("implementation_stage", "mention_only")
    score = MATURITY_SCORES.get(stage, 1)

    # Tag bonuses
    for tag in record.get("evidence_tags", []):
        score += TAG_BONUSES.get(tag, 0)

    # Support bonifiers
    if record.get("quantitative_support", False):
        score += 1
    if record.get("oversight_support", False):
        score += 1

    # Cap at documented maximum (defensive)
    score = min(score, DOCUMENTED_MAX_SCORE)

    # Map to strength
    if score <= WEAK_MAX:
        strength = "weak"
    elif score <= MODERATE_MAX:
        strength = "moderate"
    else:
        strength = "strong"

    return score, strength


def score_evidence_node(state: PipelineState) -> dict:
    """
    Score all validated evidence items deterministically.

    Updates each validated record in-place (returns new list with scores set).

    Returns partial state update:
        validated_evidence: List[EvidenceRecord] (with computed_score / computed_strength)
        errors: accumulated errors list
    """
    existing_errors = list(state.get("errors", []))
    validated = state.get("validated_evidence", [])

    if not validated:
        logger.warning("score_evidence: no validated evidence to score.")
        return {"validated_evidence": [], "errors": existing_errors}

    logger.info("Node: score_evidence — scoring %d evidence items.", len(validated))

    scored: List[EvidenceRecord] = []
    score_distribution = {"weak": 0, "moderate": 0, "strong": 0}

    for record in validated:
        raw_score, strength = _compute_score(record)
        updated = {
            **record,
            "computed_score": raw_score,
            "computed_strength": strength,
        }
        scored.append(updated)
        score_distribution[strength] += 1

    logger.info(
        "score_evidence: weak=%d, moderate=%d, strong=%d",
        score_distribution["weak"],
        score_distribution["moderate"],
        score_distribution["strong"],
    )

    return {"validated_evidence": scored, "errors": existing_errors}
