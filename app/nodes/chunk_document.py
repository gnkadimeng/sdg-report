"""
LangGraph node: chunk_document

Converts extracted pages into semantically coherent chunks.
Returns: chunks, errors
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.schemas.state import PipelineState
from app.utils.chunker import chunk_pages
from app.utils.logger import get_logger

logger = get_logger(__name__)


def chunk_document_node(state: PipelineState, config: RunnableConfig | None = None) -> dict:
    """
    Chunk the extracted pages.

    Config may optionally carry chunking parameters under
    config["configurable"] (LangGraph convention), but defaults from
    the config.yaml are used if not provided.

    Returns partial state update:
        chunks: List[ChunkRecord]
        errors: accumulated errors list
    """
    existing_errors = list(state.get("errors", []))
    pages = state.get("pages", [])

    if not pages:
        msg = "chunk_document: no pages in state — skipping chunking."
        logger.warning(msg)
        return {"chunks": [], "errors": existing_errors + [msg]}

    # Pull chunking config from LangGraph configurable dict if present
    cfg = state.get("pipeline_config") or (config or {}).get("configurable", {})
    max_chunk_tokens = int(cfg.get("max_chunk_tokens", 600))
    overlap_tokens = int(cfg.get("overlap_tokens", 80))
    min_chunk_tokens = int(cfg.get("min_chunk_tokens", 50))
    prefer_section_boundaries = bool(cfg.get("prefer_section_boundaries", True))

    logger.info("Node: chunk_document — chunking %d pages.", len(pages))

    try:
        chunks = chunk_pages(
            pages,
            max_chunk_tokens=max_chunk_tokens,
            overlap_tokens=overlap_tokens,
            min_chunk_tokens=min_chunk_tokens,
            prefer_section_boundaries=prefer_section_boundaries,
        )
    except Exception as exc:
        msg = f"chunk_document failed: {exc}"
        logger.exception(msg)
        return {"chunks": [], "errors": existing_errors + [msg]}

    logger.info("chunk_document: produced %d chunks.", len(chunks))
    return {"chunks": chunks, "errors": existing_errors}
