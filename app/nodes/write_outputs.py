"""
LangGraph node: write_outputs

Writes three output formats to the configured output directory:
    <run_id>/evidence.json          — full structured output
    <run_id>/evidence.csv           — flat evidence table
    <run_id>/report.md              — human-readable markdown summary

The run directory is named: <company>_<report_year>_<timestamp>
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.schemas.state import EvidenceRecord, PipelineState, SDGSummary
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

_ASSESSMENT_LABELS = {
    "measurable_implementation_evidence": "Strong — Measurable Implementation Evidence Present",
    "implementation_in_progress": "Moderate — Active Implementation Underway",
    "strategic_commitment_present": "Moderate — Strategic Commitment Present",
    "symbolic_alignment_only": "Weak — Symbolic Alignment Only",
    "no_evidence_found": "None — No SDG Evidence Extracted",
}

_STRENGTH_EMOJI = {
    "strong": "🟢",
    "moderate": "🟡",
    "weak": "🔴",
}


def _markdown_report(state: PipelineState) -> str:
    """Generate the full markdown summary report."""
    company = state["company"]
    report_name = state["report_name"]
    report_year = state["report_year"]
    overall = state.get("overall_assessment", "unknown")
    summaries: List[SDGSummary] = state.get("sdg_summaries", [])
    validated: List[EvidenceRecord] = state.get("validated_evidence", [])
    rejected: List[EvidenceRecord] = state.get("rejected_evidence", [])
    errors: List[str] = state.get("errors", [])

    assessment_label = _ASSESSMENT_LABELS.get(overall, overall)

    lines: List[str] = []

    # Header
    lines.append(f"# SDG Evidence Report: {company}")
    lines.append(f"**Report:** {report_name} ({report_year})")
    lines.append(
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    lines.append("")

    # Caveats box
    lines.append("---")
    lines.append("## Caveats and Methodology Notes")
    lines.append("")
    lines.append(
        "> This report is produced by an automated evidence-extraction system. "
        "It identifies text-supported indicators of SDG alignment. "
        "It does **not** provide investment advice, audit opinions, or "
        "independent verification of company claims. "
        "Evidence strength scores are computed deterministically from "
        "structured fields; they reflect textual evidence quality, not "
        "real-world impact. All evidence items include page citations "
        "from the original report."
    )
    lines.append("")

    # Executive summary
    lines.append("---")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"**Overall Assessment:** {assessment_label}")
    lines.append("")
    lines.append(
        f"- **SDGs covered:** {len(summaries)}"
    )
    lines.append(f"- **Valid evidence items:** {len(validated)}")
    lines.append(f"- **Rejected items:** {len(rejected)}")

    if validated:
        avg = sum(e.get("computed_score", 0) for e in validated) / len(validated)
        strong = sum(1 for e in validated if e.get("computed_strength") == "strong")
        moderate = sum(1 for e in validated if e.get("computed_strength") == "moderate")
        weak = sum(1 for e in validated if e.get("computed_strength") == "weak")
        lines.append(f"- **Average evidence score:** {avg:.1f} / 12")
        lines.append(
            f"- **Strength distribution:** "
            f"strong={strong}, moderate={moderate}, weak={weak}"
        )
    lines.append("")

    # SDG-by-SDG summaries
    lines.append("---")
    lines.append("## SDG-by-SDG Summary")
    lines.append("")

    if not summaries:
        lines.append("*No SDG evidence was extracted.*")
    else:
        for s in summaries:
            lines.append(f"### {s['sdg']}")
            lines.append(
                f"- **Evidence items:** {s['evidence_count']}"
            )
            lines.append(
                f"- **Average score:** {s['average_score']:.1f}"
            )
            lines.append(
                f"- **Implementation profile:** {s['implementation_profile']}"
            )
            if s["strongest_pages"]:
                page_refs = ", ".join(f"p.{p}" for p in s["strongest_pages"])
                lines.append(f"- **Key pages:** {page_refs}")
            lines.append(f"- {s['summary']}")
            lines.append("")

    # Strongest evidence items
    lines.append("---")
    lines.append("## Strongest Evidence Items")
    lines.append("")

    strong_items = sorted(
        [e for e in validated if e.get("computed_strength") == "strong"],
        key=lambda e: e.get("computed_score", 0),
        reverse=True,
    )[:10]

    if not strong_items:
        lines.append(
            "*No evidence items reached the 'strong' threshold "
            "(score ≥ 6). See all items in evidence.json.*"
        )
    else:
        for e in strong_items:
            sdgs = ", ".join(e.get("candidate_sdgs", []))
            tags = ", ".join(e.get("evidence_tags", []))
            score = e.get("computed_score", 0)
            page = e.get("page_number", "?")
            stage = e.get("implementation_stage", "")
            lines.append(
                f"**[p.{page}] {sdgs}** — Score {score}/12 "
                f"| `{stage}` | {tags}"
            )
            lines.append(f"> {e.get('evidence_summary', '')}")
            lines.append(f"> *\"{e.get('evidence_text', '')[:200]}…\"*")
            lines.append("")

    # Moderate evidence (summary table)
    moderate_items = [
        e for e in validated if e.get("computed_strength") == "moderate"
    ]
    if moderate_items:
        lines.append("---")
        lines.append(f"## Moderate Evidence ({len(moderate_items)} items)")
        lines.append("")
        lines.append("| Page | SDGs | Tags | Stage | Score |")
        lines.append("|------|------|------|-------|-------|")
        for e in sorted(
            moderate_items, key=lambda x: x.get("computed_score", 0), reverse=True
        )[:20]:
            sdgs = ", ".join(e.get("candidate_sdgs", []))
            tags = ", ".join(e.get("evidence_tags", []))
            stage = e.get("implementation_stage", "")
            score = e.get("computed_score", 0)
            page = e.get("page_number", "?")
            lines.append(f"| p.{page} | {sdgs} | {tags} | {stage} | {score} |")
        lines.append("")

    # Rejected evidence notes
    lines.append("---")
    lines.append("## Rejected / Uncertain Evidence")
    lines.append("")
    if not rejected:
        lines.append("*No evidence items were rejected.*")
    else:
        lines.append(
            f"**{len(rejected)} items were rejected** by deterministic validation. "
            "Common reasons:"
        )
        lines.append("")
        reason_counts: Dict[str, int] = {}
        for e in rejected:
            for err in e.get("validation_errors", []):
                first_word = err.split(":")[0].split("(")[0].strip()[:60]
                reason_counts[first_word] = reason_counts.get(first_word, 0) + 1
        for reason, count in sorted(
            reason_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]:
            lines.append(f"- `{reason}` ({count}×)")
        lines.append("")
        lines.append(
            "*Full rejected items are included in evidence.json "
            "(include_rejected_in_json=true).*"
        )

    # Pipeline errors
    if errors:
        lines.append("---")
        lines.append("## Pipeline Errors")
        lines.append("")
        for err in errors:
            lines.append(f"- `{err}`")
        lines.append("")

    lines.append("---")
    lines.append(
        "*Report generated by sdg-evidence-extractor. "
        "Evidence strength is assessed by deterministic rules, "
        "not LLM opinion. Page citations reference the original source document.*"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV generation
# ---------------------------------------------------------------------------

_CSV_FIELDS = [
    "evidence_id",
    "company",
    "report_name",
    "report_year",
    "page_number",
    "section_heading",
    "candidate_sdgs",
    "evidence_tags",
    "implementation_stage",
    "quantitative_support",
    "oversight_support",
    "confidence",
    "computed_score",
    "computed_strength",
    "validation_status",
    "evidence_summary",
    "evidence_text",
    "rationale",
    "validation_errors",
]


def _flatten_record(record: EvidenceRecord) -> Dict[str, Any]:
    """Flatten list fields to pipe-separated strings for CSV."""
    flat = dict(record)
    flat["candidate_sdgs"] = " | ".join(record.get("candidate_sdgs", []))
    flat["evidence_tags"] = " | ".join(record.get("evidence_tags", []))
    flat["validation_errors"] = " | ".join(record.get("validation_errors", []))
    # Truncate very long text fields
    flat["evidence_text"] = (record.get("evidence_text") or "")[:500]
    flat["rationale"] = (record.get("rationale") or "")[:300]
    return flat


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


def write_outputs_node(state: PipelineState) -> dict:
    """
    Write JSON, CSV, and markdown outputs to the output directory.

    Output directory structure:
        <output_dir>/<company>_<year>_<timestamp>/
            evidence.json
            evidence.csv
            report.md

    Returns partial state update:
        errors: accumulated errors list
    """
    existing_errors = list(state.get("errors", []))

    company_slug = state["company"].lower().replace(" ", "_")[:30]
    year = state.get("report_year", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir_name = f"{company_slug}_{year}_{timestamp}"

    base_output_dir = Path(state.get("output_dir", "data/outputs"))
    run_dir = base_output_dir / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Node: write_outputs — writing to '%s'", run_dir)
    node_errors = []

    # --- JSON ---
    try:
        validated = state.get("validated_evidence", [])
        rejected = state.get("rejected_evidence", [])

        json_payload = {
            "company": state["company"],
            "report_name": state["report_name"],
            "report_year": state["report_year"],
            "overall_assessment": state.get("overall_assessment", ""),
            "sdg_summaries": state.get("sdg_summaries", []),
            "validated_evidence": validated,
            "rejected_evidence": rejected,
            "pipeline_errors": state.get("errors", []),
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "valid_count": len(validated),
                "rejected_count": len(rejected),
                "sdg_count": len(state.get("sdg_summaries", [])),
            },
        }

        json_path = run_dir / "evidence.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_payload, f, indent=2, ensure_ascii=False)
        logger.info("JSON written: %s", json_path)
    except Exception as exc:
        err = f"write_outputs: JSON write failed: {exc}"
        logger.error(err)
        node_errors.append(err)

    # --- CSV ---
    try:
        all_evidence = state.get("validated_evidence", []) + state.get(
            "rejected_evidence", []
        )
        csv_path = run_dir / "evidence.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=_CSV_FIELDS, extrasaction="ignore"
            )
            writer.writeheader()
            for record in all_evidence:
                writer.writerow(_flatten_record(record))
        logger.info("CSV written: %s", csv_path)
    except Exception as exc:
        err = f"write_outputs: CSV write failed: {exc}"
        logger.error(err)
        node_errors.append(err)

    # --- Markdown ---
    try:
        md_content = _markdown_report(state)
        md_path = run_dir / "report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info("Markdown report written: %s", md_path)
    except Exception as exc:
        err = f"write_outputs: Markdown write failed: {exc}"
        logger.error(err)
        node_errors.append(err)

    logger.info("write_outputs: all outputs written to '%s'.", run_dir)

    return {"errors": existing_errors + node_errors}
