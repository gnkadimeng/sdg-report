"""
LangGraph node: retrieve_candidate_chunks

Embeds all chunks and retrieves the top-k most SDG-relevant ones
using hybrid scoring (semantic + keyword + boilerplate penalty).

Returns: retrieved_chunks, errors
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.retrieval.embeddings import OllamaEmbedder
from app.retrieval.hybrid_retrieval import HybridRetriever
from app.schemas.state import PipelineState
from app.utils.logger import get_logger

logger = get_logger(__name__)


def retrieve_candidate_chunks_node(
    state: PipelineState, config: RunnableConfig | None = None
) -> dict:
    """
    Build embedding index over all chunks, then retrieve top-k.

    Returns partial state update:
        retrieved_chunks: List[ChunkRecord]
        errors: accumulated errors list
    """
    existing_errors = list(state.get("errors", []))
    chunks = state.get("chunks", [])

    if not chunks:
        msg = "retrieve_candidate_chunks: no chunks in state — skipping retrieval."
        logger.warning(msg)
        return {"retrieved_chunks": [], "errors": existing_errors + [msg]}

    cfg = state.get("pipeline_config") or (config or {}).get("configurable", {})
    embedding_model = cfg.get("embedding_model", "nomic-embed-text")
    base_url = cfg.get("base_url", "http://localhost:11434")
    top_k = int(cfg.get("top_k", 20))
    semantic_weight = float(cfg.get("semantic_weight", 0.6))
    keyword_weight = float(cfg.get("keyword_weight", 0.4))
    boilerplate_penalty = float(cfg.get("boilerplate_penalty", 0.3))
    min_retrieval_score = float(cfg.get("min_retrieval_score", 0.15))
    embedding_timeout = int(cfg.get("embedding_timeout", 60))

    logger.info(
        "Node: retrieve_candidate_chunks — %d chunks, model: %s, top_k: %d",
        len(chunks),
        embedding_model,
        top_k,
    )

    try:
        embedder = OllamaEmbedder(
            model=embedding_model,
            base_url=base_url,
            timeout=embedding_timeout,
        )
        retriever = HybridRetriever(
            embedder=embedder,
            top_k=top_k,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
            boilerplate_penalty=boilerplate_penalty,
            min_retrieval_score=min_retrieval_score,
        )
        retriever.build_index(chunks)
        retrieved = retriever.retrieve()
    except Exception as exc:
        msg = f"retrieve_candidate_chunks failed: {exc}"
        logger.exception(msg)
        return {"retrieved_chunks": [], "errors": existing_errors + [msg]}

    logger.info(
        "retrieve_candidate_chunks: retrieved %d / %d chunks.",
        len(retrieved),
        len(chunks),
    )
    return {"retrieved_chunks": retrieved, "errors": existing_errors}
