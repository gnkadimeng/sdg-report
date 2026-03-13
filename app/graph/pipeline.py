"""
LangGraph pipeline definition.

Graph topology (linear — no branching in MVP):

    START
    → ingest_pdf
    → chunk_document
    → retrieve_candidate_chunks
    → extract_evidence
    → validate_evidence
    → score_evidence
    → aggregate_findings
    → write_outputs
    → END

Phase 2 TODO:
    - Add LangGraph checkpointing (SqliteSaver or PostgresSaver)
    - Add conditional branching if PDF has zero extractable text
      (could route to a fallback OCR node)
    - Add parallel extraction for large documents

Config is passed to nodes via the LangGraph "configurable" mechanism:
    graph.invoke(state, config={"configurable": {...}})
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.nodes.aggregate_findings import aggregate_findings_node
from app.nodes.chunk_document import chunk_document_node
from app.nodes.extract_evidence import extract_evidence_node
from app.nodes.ingest_pdf import ingest_pdf_node
from app.nodes.retrieve_chunks import retrieve_candidate_chunks_node
from app.nodes.score_evidence import score_evidence_node
from app.nodes.validate_evidence import validate_evidence_node
from app.nodes.write_outputs import write_outputs_node
from app.schemas.state import PipelineState
from app.utils.logger import get_logger

logger = get_logger(__name__)


def build_pipeline():
    """
    Compile and return the SDG evidence extraction LangGraph pipeline.

    Returns:
        A compiled LangGraph graph ready to invoke.
    """
    graph = StateGraph(PipelineState)

    # Register nodes
    graph.add_node("ingest_pdf", ingest_pdf_node)
    graph.add_node("chunk_document", chunk_document_node)
    graph.add_node("retrieve_candidate_chunks", retrieve_candidate_chunks_node)
    graph.add_node("extract_evidence", extract_evidence_node)
    graph.add_node("validate_evidence", validate_evidence_node)
    graph.add_node("score_evidence", score_evidence_node)
    graph.add_node("aggregate_findings", aggregate_findings_node)
    graph.add_node("write_outputs", write_outputs_node)

    # Linear edges
    graph.add_edge(START, "ingest_pdf")
    graph.add_edge("ingest_pdf", "chunk_document")
    graph.add_edge("chunk_document", "retrieve_candidate_chunks")
    graph.add_edge("retrieve_candidate_chunks", "extract_evidence")
    graph.add_edge("extract_evidence", "validate_evidence")
    graph.add_edge("validate_evidence", "score_evidence")
    graph.add_edge("score_evidence", "aggregate_findings")
    graph.add_edge("aggregate_findings", "write_outputs")
    graph.add_edge("write_outputs", END)

    compiled = graph.compile()
    logger.info("Pipeline compiled successfully.")
    return compiled


def run_pipeline(
    pdf_path: str,
    company: str,
    report_name: str,
    report_year: int,
    output_dir: str = "data/outputs",
    config: dict | None = None,
) -> PipelineState:
    """
    Convenience wrapper to run the full pipeline.

    Args:
        pdf_path:    Path to the PDF report.
        company:     Company name.
        report_name: Report title.
        report_year: Report publication year.
        output_dir:  Directory for output files.
        config:      Optional LangGraph configurable dict
                     (model names, thresholds, etc.).

    Returns:
        Final PipelineState after all nodes have run.
    """
    initial_state: PipelineState = {
        "company": company,
        "report_name": report_name,
        "report_year": report_year,
        "input_pdf_path": pdf_path,
        "output_dir": output_dir,
        "pipeline_config": config or {},
        "pages": [],
        "chunks": [],
        "retrieved_chunks": [],
        "extracted_evidence": [],
        "validated_evidence": [],
        "rejected_evidence": [],
        "sdg_summaries": [],
        "overall_assessment": "",
        "errors": [],
    }

    invoke_config = {}
    if config:
        invoke_config["configurable"] = config

    pipeline = build_pipeline()

    logger.info(
        "Running pipeline: company='%s', report='%s' (%d), pdf='%s'",
        company,
        report_name,
        report_year,
        pdf_path,
    )

    final_state: PipelineState = pipeline.invoke(
        initial_state, config=invoke_config if invoke_config else None
    )

    logger.info(
        "Pipeline complete. validated=%d, rejected=%d, sdgs=%d, assessment='%s'",
        len(final_state.get("validated_evidence", [])),
        len(final_state.get("rejected_evidence", [])),
        len(final_state.get("sdg_summaries", [])),
        final_state.get("overall_assessment", ""),
    )

    return final_state
