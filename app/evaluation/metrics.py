"""
Evaluation metrics for the SDG evidence extraction pipeline.

Metrics computed:
    - retrieval_recall_at_k:      Were relevant chunks retrieved?
    - sdg_set_overlap_accuracy:   Jaccard similarity of predicted vs expected SDGs
    - evidence_tag_accuracy:      Jaccard similarity of predicted vs expected tags
    - implementation_stage_accuracy: Exact match for implementation stage
    - quantitative_support_accuracy: Exact match
    - oversight_support_accuracy:    Exact match
    - validation_pass_accuracy:   Did valid items pass, invalid items fail?
    - over_claim_rate:            Rate of unsupported positive claims

Over-claim is defined as any of:
    - SDG assigned without textual basis (model confidence < 0.4 AND no keywords)
    - quantitative_support=True without numeric evidence in text
    - oversight_support=True without oversight wording in text
    - implementation_stage stronger than expected

All metrics are deterministic Python computations over structured records.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(r"\b\d[\d,.]*\s*(%|tonne|mt|gwh|mwh|kwh|m[³3]|kg|litres?|l\b)")
_OVERSIGHT_RE = re.compile(
    r"\b(board|committee|executive|ceo|cfo|director|oversight|audit|governance)\b",
    re.IGNORECASE,
)

STAGE_ORDER = {
    "mention_only": 0,
    "planned_action": 1,
    "implementation_in_progress": 2,
    "implemented_with_measurable_evidence": 3,
}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    """Jaccard similarity coefficient for two sets."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


# ---------------------------------------------------------------------------
# Individual metric functions
# ---------------------------------------------------------------------------


def retrieval_recall_at_k(
    retrieved_chunk_ids: List[str],
    expected_chunk_ids: List[str],
    k: int,
) -> float:
    """
    Fraction of expected chunks that appear in the top-k retrieved chunks.

    Args:
        retrieved_chunk_ids: Ordered list of retrieved chunk IDs (best first).
        expected_chunk_ids:  Ground-truth relevant chunk IDs.
        k:                   Cut-off rank.

    Returns:
        Recall@k in [0.0, 1.0]. Returns 1.0 if expected is empty.
    """
    if not expected_chunk_ids:
        return 1.0
    top_k_set = set(retrieved_chunk_ids[:k])
    expected_set = set(expected_chunk_ids)
    hits = len(top_k_set & expected_set)
    return hits / len(expected_set)


def sdg_set_overlap_accuracy(
    predicted_sdgs: List[str],
    expected_sdgs: List[str],
) -> float:
    """Jaccard similarity between predicted and expected SDG sets."""
    return _jaccard(set(predicted_sdgs), set(expected_sdgs))


def evidence_tag_accuracy(
    predicted_tags: List[str],
    expected_tags: List[str],
) -> float:
    """Jaccard similarity between predicted and expected evidence tag sets."""
    return _jaccard(set(predicted_tags), set(expected_tags))


def implementation_stage_accuracy(
    predicted_stage: str,
    expected_stage: str,
) -> bool:
    """Exact match on implementation stage."""
    return predicted_stage == expected_stage


def implementation_stage_is_overclaim(
    predicted_stage: str,
    expected_stage: str,
) -> bool:
    """
    True if the predicted stage is stronger than the expected stage.
    This is an over-claim.
    """
    pred_rank = STAGE_ORDER.get(predicted_stage, -1)
    exp_rank = STAGE_ORDER.get(expected_stage, -1)
    return pred_rank > exp_rank


def quantitative_support_accuracy(
    predicted: bool,
    expected: bool,
) -> bool:
    return predicted == expected


def oversight_support_accuracy(
    predicted: bool,
    expected: bool,
) -> bool:
    return predicted == expected


def validation_pass_accuracy(
    validation_status: str,
    expected_valid: bool,
) -> bool:
    """True if the validation decision matches expected_valid."""
    item_is_valid = validation_status == "valid"
    return item_is_valid == expected_valid


def is_quantitative_overclaim(evidence_text: str, predicted_quant: bool) -> bool:
    """
    True if quantitative_support=True but no numeric/metric pattern
    is found in the evidence text.
    """
    if not predicted_quant:
        return False
    return not bool(_NUMERIC_RE.search(evidence_text))


def is_oversight_overclaim(evidence_text: str, predicted_oversight: bool) -> bool:
    """
    True if oversight_support=True but no oversight wording is found.
    """
    if not predicted_oversight:
        return False
    return not bool(_OVERSIGHT_RE.search(evidence_text))


def is_stage_overclaim(predicted_stage: str, expected_stage: str) -> bool:
    return implementation_stage_is_overclaim(predicted_stage, expected_stage)


# ---------------------------------------------------------------------------
# Aggregate over a result set
# ---------------------------------------------------------------------------


def compute_aggregate_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute aggregate metrics over a list of per-item evaluation results.

    Each item in results should be a dict with keys:
        sdg_jaccard, tag_jaccard, stage_exact, stage_overclaim,
        quant_exact, oversight_exact, validation_correct,
        quant_overclaim, oversight_overclaim

    Returns:
        Dict of aggregate metric values.
    """
    if not results:
        return {}

    n = len(results)

    def _mean(key: str) -> float:
        vals = [r[key] for r in results if key in r]
        return sum(vals) / len(vals) if vals else 0.0

    def _rate(key: str) -> float:
        vals = [r[key] for r in results if key in r]
        return sum(1 for v in vals if v) / len(vals) if vals else 0.0

    over_claim_flags = [
        r.get("stage_overclaim", False)
        or r.get("quant_overclaim", False)
        or r.get("oversight_overclaim", False)
        for r in results
    ]
    over_claim_rate = sum(over_claim_flags) / n if n > 0 else 0.0

    return {
        "n": n,
        "sdg_jaccard_mean": round(_mean("sdg_jaccard"), 3),
        "tag_jaccard_mean": round(_mean("tag_jaccard"), 3),
        "stage_exact_rate": round(_rate("stage_exact"), 3),
        "stage_overclaim_rate": round(_rate("stage_overclaim"), 3),
        "quant_exact_rate": round(_rate("quant_exact"), 3),
        "oversight_exact_rate": round(_rate("oversight_exact"), 3),
        "validation_accuracy": round(_rate("validation_correct"), 3),
        "over_claim_rate": round(over_claim_rate, 3),
    }
