"""
Ollama embedding client.

Wraps the Ollama Python SDK to produce NumPy embedding vectors.
All embedding calls go through this module to allow easy model switching.
"""

from __future__ import annotations

import time
from typing import List

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)


class OllamaEmbedder:
    """
    Thin wrapper around the Ollama embeddings API.

    Args:
        model:      Ollama model name (e.g. "nomic-embed-text").
        base_url:   Ollama server URL.
        timeout:    Request timeout in seconds.
        max_retries: Number of retry attempts on failure.
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: int = 60,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries

        try:
            import ollama as _ollama  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "ollama package required: pip install ollama"
            ) from exc

    def _get_client(self):
        import ollama
        return ollama.Client(host=self.base_url)

    def embed_text(self, text: str) -> np.ndarray:
        """
        Embed a single text string.

        Args:
            text: Text to embed. Will be truncated to first 8000 chars
                  if very long (practical limit for most embedding models).

        Returns:
            1-D NumPy float32 array.

        Raises:
            RuntimeError: If all retries fail.
        """
        truncated = text[:8000]
        client = self._get_client()

        last_error: Exception = RuntimeError("No attempts made")
        for attempt in range(1, self.max_retries + 1):
            try:
                response = client.embeddings(model=self.model, prompt=truncated)
                vector = response["embedding"]
                return np.array(vector, dtype=np.float32)
            except Exception as exc:
                last_error = exc
                wait = 2 ** attempt
                logger.warning(
                    "Embedding attempt %d/%d failed: %s. Retrying in %ds…",
                    attempt,
                    self.max_retries,
                    exc,
                    wait,
                )
                time.sleep(wait)

        raise RuntimeError(
            f"Embedding failed after {self.max_retries} attempts: {last_error}"
        )

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Embed a list of texts sequentially.

        Ollama does not currently support true batch embedding, so this
        iterates and calls embed_text for each item.

        Args:
            texts: List of strings to embed.

        Returns:
            List of 1-D NumPy float32 arrays (same length as input).
        """
        vectors: List[np.ndarray] = []
        for i, text in enumerate(texts):
            if i % 10 == 0 and i > 0:
                logger.debug("Embedding progress: %d / %d", i, len(texts))
            vectors.append(self.embed_text(text))
        logger.debug("Embedded %d texts with model '%s'.", len(vectors), self.model)
        return vectors


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Return cosine similarity between two 1-D vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
