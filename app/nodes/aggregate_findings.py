"""
LangGraph node: aggregate_findings

Aggregates validated, scored evidence by SDG.
All logic is deterministic — no LLM involvement.

Overall assessment tiers (deterministic, in priority order):
    1. "measurable_implementation_evidence"
       → any evidence with stage=implemented_with_measurable_evidence
         AND quantitative_support=True
    2. "implementation_in_progress"
       → any evidence with stage=implementation_in_progress
    3. "strategic_commitment_present"
       → any evidence with tags containing "policy" or "governance"
    4. "symbolic_alignment_only"
       → everything else (mentions, aspirations only)

Implementation profile per SDG (deterministic):
    Derived from the distribution of implementation_stage values for that SDG.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Dict, List

from app.schemas.state import EvidenceRecord, PipelineState, SDGSummary
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _dominant_stage(stages: List[str]) -> str:
    """Return the most advanced implementation stage present."""
    stage_order = [
        "implemented_with_measurable_evidence",
        "implementation_in_progress",
        "planned_action",
        "mention_only",
    ]
    for s in stage_order:
        if s in stages:
            return s
    return "mention_only"


def _implementation_profile(stages: List[str]) -> str:
    """
    Describe the implementation stage distribution as a concise label.

    Checks for the highest stage present.
    """
    stage_counter = Counter(stages)
    total = sum(stage_counter.values())
    dominant = _dominant_stage(stages)

    if dominant == "implemented_with_measurable_evidence":
        pct = round(100 * stage_counter[dominant] / total)
        return f"measurable_evidence ({pct}% of items)"
    elif dominant == "implementation_in_progress":
        pct = round(100 * stage_counter[dominant] / total)
        return f"in_progress ({pct}% of items)"
    elif dominant == "planned_action":
        pct = round(100 * stage_counter[dominant] / total)
        return f"planned ({pct}% of items)"
    else:
        return "mentions_only"


def _overall_assessment(evidence: List[EvidenceRecord]) -> str:
    """
    Deterministically assign an overall assessment label.

    Checks in priority order — returns the highest tier supported by evidence.
    """
    if not evidence:
        return "no_evidence_found"

    # Tier 1: measured implementation
    for e in evidence:
        if (
            e.get("implementation_stage") == "implemented_with_measurable_evidence"
            and e.get("quantitative_support", False)
        ):
            return "measurable_implementation_evidence"

    # Tier 2: active implementation
    for e in evidence:
        if e.get("implementation_stage") == "implementation_in_progress":
            return "implementation_in_progress"

    # Tier 3: strategic commitment
    for e in evidence:
        tags = e.get("evidence_tags", [])
        if "policy" in tags or "governance" in tags:
            return "strategic_commitment_present"

    # Tier 4: default
    return "symbolic_alignment_only"


def _build_sdg_summary(sdg: str, items: List[EvidenceRecord]) -> SDGSummary:
    """Build a SDGSummary for a single SDG from its evidence items."""
    scores = [e.get("computed_score", 1) for e in items]
    avg_score = round(statistics.mean(scores), 2) if scores else 0.0

    stages = [e.get("implementation_stage", "mention_only") for e in items]
    profile = _implementation_profile(stages)

    # Top pages: pages from the top-3 highest-scoring items
    sorted_items = sorted(items, key=lambda e: e.get("computed_score", 0), reverse=True)
    strongest_pages = []
    seen_pages = set()
    for e in sorted_items[:5]:
        p = e.get("page_number")
        if p and p not in seen_pages:
            strongest_pages.append(p)
            seen_pages.add(p)

    # Deterministic summary text
    stage_counts = Counter(stages)
    tag_pool = []
    for e in items:
        tag_pool.extend(e.get("evidence_tags", []))
    top_tags = [t for t, _ in Counter(tag_pool).most_common(4)]

    summary_parts = [
        f"{len(items)} evidence item(s) found.",
        f"Dominant stage: {_dominant_stage(stages).replace('_', ' ')}.",
        f"Average score: {avg_score}/{10}.",  # contextualise against ~10
    ]
    if top_tags:
        summary_parts.append(f"Key evidence types: {', '.join(top_tags)}.")

    return SDGSummary(
        sdg=sdg,
        evidence_count=len(items),
        average_score=avg_score,
        strongest_pages=strongest_pages,
        implementation_profile=profile,
        summary=" ".join(summary_parts),
    )


def aggregate_findings_node(state: PipelineState) -> dict:
    """
    Group validated evidence by SDG and produce SDGSummary records.
    Compute overall assessment deterministically.

    Returns partial state update:
        sdg_summaries: List[SDGSummary]
        overall_assessment: str
        errors: accumulated errors list
    """
    existing_errors = list(state.get("errors", []))
    validated = state.get("validated_evidence", [])

    logger.info(
        "Node: aggregate_findings — aggregating %d validated evidence items.",
        len(validated),
    )

    # Group by SDG
    by_sdg: Dict[str, List[EvidenceRecord]] = defaultdict(list)
    for record in validated:
        for sdg in record.get("candidate_sdgs", []):
            by_sdg[sdg].append(record)

    # Sort SDGs numerically
    def sdg_sort_key(sdg: str) -> int:
        try:
            return int(sdg.replace("SDG", "").strip())
        except ValueError:
            return 99

    summaries: List[SDGSummary] = []
    for sdg in sorted(by_sdg.keys(), key=sdg_sort_key):
        summary = _build_sdg_summary(sdg, by_sdg[sdg])
        summaries.append(summary)
        logger.debug(
            "SDG %s: %d items, avg score %.2f, profile: %s",
            sdg,
            summary["evidence_count"],
            summary["average_score"],
            summary["implementation_profile"],
        )

    overall = _overall_assessment(validated)

    logger.info(
        "aggregate_findings: %d SDGs covered, overall assessment: '%s'.",
        len(summaries),
        overall,
    )

    return {
        "sdg_summaries": summaries,
        "overall_assessment": overall,
        "errors": existing_errors,
    }
