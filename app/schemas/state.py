"""
LangGraph pipeline state definitions using TypedDict.

All state fields are defined here. Nodes receive PipelineState and return
partial dicts — LangGraph merges them into the state at each step.
"""

from __future__ import annotations

from typing import Any, Dict, List

from typing_extensions import NotRequired, TypedDict


# ---------------------------------------------------------------------------
# Sub-record types
# ---------------------------------------------------------------------------


class ReportPage(TypedDict):
    """One extracted PDF page."""

    page_number: int
    text: str
    section_heading: NotRequired[str]  # detected heading for this page, if any


class ChunkRecord(TypedDict):
    """One semantically coherent text chunk derived from pages."""

    chunk_id: str
    page_number: int          # starting page of this chunk
    section_heading: str      # inherited or detected heading
    text: str
    retrieval_score: NotRequired[float]   # set during retrieval
    keyword_hits: NotRequired[List[str]]  # SDG keywords found in this chunk


class EvidenceRecord(TypedDict):
    """
    One extracted SDG evidence item.

    Fields set by the LLM (extraction):
        company, report_name, report_year, page_number, section_heading,
        evidence_text, evidence_summary, candidate_sdgs, evidence_tags,
        implementation_stage, quantitative_support, oversight_support,
        confidence, rationale

    Fields set by deterministic code (validation + scoring):
        evidence_id, validation_status, validation_errors,
        computed_strength, computed_score
    """

    # --- identity ---
    evidence_id: str
    company: str
    report_name: str
    report_year: int

    # --- provenance ---
    page_number: int
    section_heading: str

    # --- content ---
    evidence_text: str        # verbatim or near-verbatim excerpt
    evidence_summary: str     # one-sentence model summary

    # --- classification (LLM output) ---
    candidate_sdgs: List[str]   # e.g. ["SDG 13", "SDG 7"]
    evidence_tags: List[str]    # subset of VALID_EVIDENCE_TAGS
    implementation_stage: str   # one of VALID_IMPLEMENTATION_STAGES
    quantitative_support: bool
    oversight_support: bool
    confidence: float           # model self-reported confidence [0.0–1.0]
    rationale: str              # model explanation

    # --- validation (deterministic) ---
    validation_status: str      # "valid" | "rejected"
    validation_errors: List[str]

    # --- scoring (deterministic) ---
    computed_strength: str      # "weak" | "moderate" | "strong"
    computed_score: int         # raw integer score


class SDGSummary(TypedDict):
    """Aggregated evidence for a single SDG."""

    sdg: str
    evidence_count: int
    average_score: float
    strongest_pages: List[int]
    implementation_profile: str   # dominant implementation stage
    summary: str                  # deterministic text summary


# ---------------------------------------------------------------------------
# Top-level pipeline state
# ---------------------------------------------------------------------------


class PipelineState(TypedDict):
    """
    Complete state passed through the LangGraph pipeline.

    Nodes receive this state and return partial dicts.
    LangGraph merges returned dicts into the running state.

    Note on error accumulation:
        Each node reads state["errors"] and appends to it, then returns the
        full updated list. This avoids needing a custom reducer.
    """

    # --- inputs ---
    company: str
    report_name: str
    report_year: int
    input_pdf_path: str
    output_dir: str
    pipeline_config: Dict[str, Any]   # model names, thresholds — set at startup

    # --- pipeline stages ---
    pages: List[ReportPage]
    chunks: List[ChunkRecord]
    retrieved_chunks: List[ChunkRecord]
    extracted_evidence: List[EvidenceRecord]
    validated_evidence: List[EvidenceRecord]
    rejected_evidence: List[EvidenceRecord]

    # --- outputs ---
    sdg_summaries: List[SDGSummary]
    overall_assessment: str

    # --- diagnostics ---
    errors: List[str]
