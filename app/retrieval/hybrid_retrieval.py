"""
Hybrid retrieval: semantic similarity + keyword scoring + boilerplate penalty.

No LLM judgment is involved in retrieval scoring.
All scoring is deterministic.

Score formula (per chunk):
    combined = semantic_weight * cosine_sim + keyword_weight * keyword_score
    if is_boilerplate(chunk.text):
        combined *= boilerplate_penalty

Chunks are ranked by combined score and the top-k returned.
"""

from __future__ import annotations

from typing import List

import numpy as np

from app.retrieval.embeddings import OllamaEmbedder, cosine_similarity
from app.retrieval.lexicon import (
    SDG_QUERY_TEXT,
    get_keyword_hits,
    is_boilerplate,
)
from app.schemas.state import ChunkRecord
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Max keywords expected in a relevant chunk — used to normalise keyword score
_MAX_KEYWORDS_EXPECTED = 8


def _keyword_score(hits: List[str]) -> float:
    """Normalise keyword hit count to [0.0, 1.0]."""
    return min(len(hits) / _MAX_KEYWORDS_EXPECTED, 1.0)


class HybridRetriever:
    """
    In-memory hybrid retriever for SDG-relevant chunks.

    Build the index once per pipeline run by calling build_index(), then
    retrieve top-k chunks with retrieve().

    Args:
        embedder:          OllamaEmbedder instance.
        top_k:             Number of chunks to return.
        semantic_weight:   Weight for cosine similarity (default 0.6).
        keyword_weight:    Weight for keyword score (default 0.4).
        boilerplate_penalty: Multiplier for boilerplate chunks (default 0.3).
        min_retrieval_score: Discard chunks below this combined score.
    """

    def __init__(
        self,
        embedder: OllamaEmbedder,
        top_k: int = 20,
        semantic_weight: float = 0.6,
        keyword_weight: float = 0.4,
        boilerplate_penalty: float = 0.3,
        min_retrieval_score: float = 0.15,
    ) -> None:
        self.embedder = embedder
        self.top_k = top_k
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        self.boilerplate_penalty = boilerplate_penalty
        self.min_retrieval_score = min_retrieval_score

        self._chunks: List[ChunkRecord] = []
        self._embeddings: List[np.ndarray] = []
        self._query_vector: np.ndarray | None = None

    def build_index(self, chunks: List[ChunkRecord]) -> None:
        """
        Embed all chunks and the SDG query string.

        This is called once per pipeline run. Embeddings are stored in memory.

        Args:
            chunks: All chunks produced by the chunker.
        """
        if not chunks:
            logger.warning("No chunks to index.")
            self._chunks = []
            self._embeddings = []
            return

        logger.info(
            "Building retrieval index for %d chunks (model: %s)…",
            len(chunks),
            self.embedder.model,
        )

        texts = [c["text"] for c in chunks]
        self._embeddings = self.embedder.embed_batch(texts)
        self._chunks = list(chunks)

        logger.debug("Embedding SDG query vector…")
        self._query_vector = self.embedder.embed_text(SDG_QUERY_TEXT)

        logger.info("Retrieval index ready.")

    def retrieve(self, extra_query: str | None = None) -> List[ChunkRecord]:
        """
        Score and rank all indexed chunks, returning top-k.

        Args:
            extra_query: Optional additional query text. If provided, a
                         combined query embedding is used (SDG_QUERY + extra).

        Returns:
            Top-k ChunkRecord dicts, each augmented with:
                retrieval_score: combined hybrid score
                keyword_hits:    list of SDG keywords found
        """
        if not self._chunks or self._query_vector is None:
            logger.warning("Index is empty — no chunks to retrieve.")
            return []

        query_vec = self._query_vector
        if extra_query:
            extra_vec = self.embedder.embed_text(extra_query)
            query_vec = (query_vec + extra_vec) / 2.0
            query_vec = query_vec / (np.linalg.norm(query_vec) or 1.0)

        scored: list[tuple[float, int, ChunkRecord]] = []

        for i, (chunk, emb) in enumerate(zip(self._chunks, self._embeddings)):
            sem_sim = cosine_similarity(query_vec, emb)
            hits = get_keyword_hits(chunk["text"])
            kw_score = _keyword_score(hits)

            combined = (
                self.semantic_weight * sem_sim
                + self.keyword_weight * kw_score
            )

            if is_boilerplate(chunk["text"]):
                combined *= self.boilerplate_penalty
                logger.debug(
                    "Boilerplate penalty applied to chunk %s (page %d)",
                    chunk["chunk_id"],
                    chunk["page_number"],
                )

            if combined >= self.min_retrieval_score:
                # Return a copy augmented with retrieval metadata
                augmented: ChunkRecord = {
                    **chunk,  # type: ignore[misc]
                    "retrieval_score": round(combined, 4),
                    "keyword_hits": hits,
                }
                scored.append((combined, i, augmented))

        # Sort descending by combined score
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [item[2] for item in scored[: self.top_k]]

        logger.info(
            "Retrieved %d / %d chunks (top-%d threshold >= %.2f).",
            len(top),
            len(self._chunks),
            self.top_k,
            self.min_retrieval_score,
        )
        return top
