"""
Evidence extraction using Ollama chat model.

The LLM is used only for extraction and normalisation.
It does NOT perform validation, scoring, or strength assessment.

Retry logic handles malformed JSON — up to max_retries attempts,
with a regex-based JSON extraction fallback before giving up.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from app.extraction.prompts import (
    EXTRACTION_RETRY_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_PROMPT_TEMPLATE,
)
from app.schemas.state import ChunkRecord, EvidenceRecord
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Fields the LLM is expected to return per evidence item
_REQUIRED_LLM_FIELDS = {
    "evidence_text",
    "evidence_summary",
    "candidate_sdgs",
    "evidence_tags",
    "implementation_stage",
    "quantitative_support",
    "oversight_support",
    "confidence",
    "rationale",
}

# Regex to find the first JSON object in a response (fallback parsing)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to parse JSON from a raw model response.

    First tries direct json.loads. Falls back to regex extraction.
    Returns None if all attempts fail.
    """
    raw = raw.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Regex fallback: find first {...} block
    match = _JSON_OBJECT_RE.search(raw)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _coerce_evidence_item(
    item: Dict[str, Any],
    chunk: ChunkRecord,
    company: str,
    report_name: str,
    report_year: int,
    max_evidence_per_chunk: int,
) -> Optional[EvidenceRecord]:
    """
    Convert a raw LLM output dict into a typed EvidenceRecord.

    Returns None if the item is missing critical fields.
    """
    missing = _REQUIRED_LLM_FIELDS - set(item.keys())
    if missing:
        logger.debug("Skipping evidence item with missing fields: %s", missing)
        return None

    evidence_text = str(item.get("evidence_text", "")).strip()
    if not evidence_text:
        return None

    candidate_sdgs = item.get("candidate_sdgs", [])
    if not isinstance(candidate_sdgs, list):
        candidate_sdgs = []

    evidence_tags = item.get("evidence_tags", [])
    if not isinstance(evidence_tags, list):
        evidence_tags = []

    confidence = item.get("confidence", 0.5)
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5

    record: EvidenceRecord = {
        "evidence_id": str(uuid.uuid4()),
        "company": company,
        "report_name": report_name,
        "report_year": report_year,
        "page_number": chunk["page_number"],
        "section_heading": chunk.get("section_heading", ""),
        "evidence_text": evidence_text,
        "evidence_summary": str(item.get("evidence_summary", "")).strip(),
        "candidate_sdgs": candidate_sdgs,
        "evidence_tags": evidence_tags,
        "implementation_stage": str(item.get("implementation_stage", "")).strip(),
        "quantitative_support": bool(item.get("quantitative_support", False)),
        "oversight_support": bool(item.get("oversight_support", False)),
        "confidence": confidence,
        "rationale": str(item.get("rationale", "")).strip(),
        # Validation and scoring filled in by downstream nodes
        "validation_status": "pending",
        "validation_errors": [],
        "computed_strength": "",
        "computed_score": 0,
    }
    return record


class EvidenceExtractor:
    """
    Calls Ollama chat model to extract structured SDG evidence from chunks.

    Args:
        model:               Ollama chat model name (e.g. "mistral").
        base_url:            Ollama server URL.
        timeout:             Request timeout in seconds.
        max_retries:         Retries for malformed JSON.
        temperature:         Sampling temperature (0.0 = deterministic).
        max_evidence_per_chunk: Cap on evidence items per chunk.
    """

    def __init__(
        self,
        model: str = "mistral",
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
        max_retries: int = 3,
        temperature: float = 0.0,
        max_evidence_per_chunk: int = 5,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.temperature = temperature
        self.max_evidence_per_chunk = max_evidence_per_chunk

        try:
            import ollama as _ollama  # noqa: F401
        except ImportError as exc:
            raise ImportError("pip install ollama") from exc

    def _get_client(self):
        import ollama
        return ollama.Client(host=self.base_url)

    def _call_model(
        self,
        messages: List[Dict[str, str]],
    ) -> str:
        """Make a chat completion call and return the raw response text."""
        client = self._get_client()
        response = client.chat(
            model=self.model,
            messages=messages,
            options={"temperature": self.temperature},
        )
        return response["message"]["content"]

    def extract(
        self,
        chunk: ChunkRecord,
        company: str,
        report_name: str,
        report_year: int,
    ) -> List[EvidenceRecord]:
        """
        Extract SDG evidence from a single chunk.

        Args:
            chunk:       The text chunk to analyse.
            company:     Company name for provenance.
            report_name: Report name for provenance.
            report_year: Report year for provenance.

        Returns:
            List of EvidenceRecord dicts (may be empty if no evidence found).
            Extraction failures are logged, not raised.
        """
        user_prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(
            company=company,
            report_name=report_name,
            report_year=report_year,
            page_number=chunk["page_number"],
            section_heading=chunk.get("section_heading", "Unknown"),
            chunk_text=chunk["text"],
        )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        parsed: Optional[Dict[str, Any]] = None
        last_raw = ""

        for attempt in range(1, self.max_retries + 1):
            try:
                raw = self._call_model(messages)
                last_raw = raw
                parsed = _try_parse_json(raw)
                if parsed is not None:
                    break
                # Ask for retry
                logger.warning(
                    "Attempt %d: malformed JSON from model for chunk %s. Retrying…",
                    attempt,
                    chunk["chunk_id"],
                )
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": EXTRACTION_RETRY_PROMPT})
                time.sleep(1)

            except Exception as exc:
                logger.warning(
                    "Attempt %d: model call failed for chunk %s: %s",
                    attempt,
                    chunk["chunk_id"],
                    exc,
                )
                time.sleep(2 ** attempt)

        if parsed is None:
            logger.error(
                "All %d extraction attempts failed for chunk %s. "
                "Last raw response (first 200 chars): %s",
                self.max_retries,
                chunk["chunk_id"],
                last_raw[:200],
            )
            return []

        raw_items = parsed.get("evidence_items", [])
        if not isinstance(raw_items, list):
            logger.warning(
                "evidence_items is not a list in response for chunk %s",
                chunk["chunk_id"],
            )
            return []

        results: List[EvidenceRecord] = []
        for item in raw_items[: self.max_evidence_per_chunk]:
            record = _coerce_evidence_item(
                item,
                chunk,
                company,
                report_name,
                report_year,
                self.max_evidence_per_chunk,
            )
            if record is not None:
                results.append(record)

        logger.debug(
            "Chunk %s → %d evidence item(s) extracted.",
            chunk["chunk_id"],
            len(results),
        )
        return results
