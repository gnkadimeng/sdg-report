"""
LangGraph node: extract_evidence

Calls the Ollama chat model for each retrieved chunk to extract
structured SDG evidence records.

Returns: extracted_evidence, errors
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.extraction.extractor import EvidenceExtractor
from app.schemas.state import PipelineState
from app.utils.logger import get_logger

logger = get_logger(__name__)


def extract_evidence_node(
    state: PipelineState, config: RunnableConfig | None = None
) -> dict:
    """
    Run LLM extraction on each retrieved chunk.

    Returns partial state update:
        extracted_evidence: List[EvidenceRecord]
        errors: accumulated errors list
    """
    existing_errors = list(state.get("errors", []))
    retrieved_chunks = state.get("retrieved_chunks", [])

    if not retrieved_chunks:
        msg = "extract_evidence: no retrieved chunks — skipping extraction."
        logger.warning(msg)
        return {"extracted_evidence": [], "errors": existing_errors + [msg]}

    cfg = state.get("pipeline_config") or (config or {}).get("configurable", {})
    chat_model = cfg.get("chat_model", "gemma2")
    base_url = cfg.get("base_url", "http://localhost:11434")
    max_retries = int(cfg.get("max_retries", 3))
    temperature = float(cfg.get("temperature", 0.0))
    max_evidence_per_chunk = int(cfg.get("max_evidence_per_chunk", 5))
    chat_timeout = int(cfg.get("chat_timeout", 120))

    company = state["company"]
    report_name = state["report_name"]
    report_year = state["report_year"]

    logger.info(
        "Node: extract_evidence — %d chunks, model: %s",
        len(retrieved_chunks),
        chat_model,
    )

    try:
        extractor = EvidenceExtractor(
            model=chat_model,
            base_url=base_url,
            timeout=chat_timeout,
            max_retries=max_retries,
            temperature=temperature,
            max_evidence_per_chunk=max_evidence_per_chunk,
        )
    except ImportError as exc:
        msg = f"extract_evidence: cannot initialise extractor: {exc}"
        logger.error(msg)
        return {"extracted_evidence": [], "errors": existing_errors + [msg]}

    all_evidence = []
    node_errors = []

    for i, chunk in enumerate(retrieved_chunks):
        logger.debug(
            "Extracting from chunk %d/%d (page %d)…",
            i + 1,
            len(retrieved_chunks),
            chunk["page_number"],
        )
        try:
            items = extractor.extract(
                chunk=chunk,
                company=company,
                report_name=report_name,
                report_year=report_year,
            )
            all_evidence.extend(items)
        except Exception as exc:
            err = f"extract_evidence: error on chunk {chunk['chunk_id']}: {exc}"
            logger.warning(err)
            node_errors.append(err)

    logger.info(
        "extract_evidence: %d evidence items extracted from %d chunks "
        "(%d chunk-level errors).",
        len(all_evidence),
        len(retrieved_chunks),
        len(node_errors),
    )

    return {
        "extracted_evidence": all_evidence,
        "errors": existing_errors + node_errors,
    }
