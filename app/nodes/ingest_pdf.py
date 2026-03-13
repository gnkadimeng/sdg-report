"""
LangGraph node: ingest_pdf

Loads and extracts text from the input PDF.
Returns: pages, errors
"""

from __future__ import annotations

from app.schemas.state import PipelineState
from app.utils.logger import get_logger
from app.utils.pdf_parser import parse_pdf

logger = get_logger(__name__)


def ingest_pdf_node(state: PipelineState) -> dict:
    """
    Extract pages from the PDF at state["input_pdf_path"].

    Returns partial state update:
        pages:  List[ReportPage]
        errors: accumulated errors list
    """
    existing_errors = list(state.get("errors", []))
    pdf_path = state["input_pdf_path"]

    logger.info("Node: ingest_pdf — loading '%s'", pdf_path)

    try:
        pages = parse_pdf(pdf_path)
    except (FileNotFoundError, RuntimeError, ImportError) as exc:
        msg = f"ingest_pdf failed: {exc}"
        logger.error(msg)
        return {"pages": [], "errors": existing_errors + [msg]}

    if not pages:
        msg = f"ingest_pdf: no pages extracted from '{pdf_path}'"
        logger.error(msg)
        return {"pages": [], "errors": existing_errors + [msg]}

    logger.info("ingest_pdf: extracted %d pages.", len(pages))
    return {"pages": pages, "errors": existing_errors}
