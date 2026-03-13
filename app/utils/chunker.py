"""
Document chunking module.

Strategy (in priority order):
1. Group consecutive pages that share the same detected section heading
   into one chunk, subject to max_chunk_tokens.
2. If a heading-group exceeds max_chunk_tokens, split it with overlapping
   sliding windows — still preserving heading + page reference.
3. If no headings are available, use sliding windows over individual pages.

Each chunk preserves: chunk_id, page_number (start page), section_heading, text.

Phase 2 TODO:
    - Parse actual document outline (PDF bookmarks) for more reliable headings
    - Sentence-boundary-aware splitting
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional

from app.schemas.state import ChunkRecord, ReportPage
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Word-to-token approximation factor
_WORDS_PER_TOKEN = 0.75  # 1 token ≈ 0.75 words  →  1 word ≈ 1.33 tokens


def _word_count(text: str) -> int:
    return len(text.split())


def _approx_tokens(text: str) -> int:
    return int(_word_count(text) / _WORDS_PER_TOKEN)


def _make_chunk_id(text: str, page: int, idx: int) -> str:
    digest = hashlib.md5(f"{page}:{idx}:{text[:80]}".encode()).hexdigest()[:8]
    return f"chunk_{page}_{idx}_{digest}"


def _split_into_windows(
    text: str,
    max_tokens: int,
    overlap_tokens: int,
    page_number: int,
    heading: str,
    start_idx: int,
) -> List[ChunkRecord]:
    """
    Split a long text block into overlapping windows.

    Args:
        text:          Full text to split.
        max_tokens:    Approximate token limit per window.
        overlap_tokens: Approximate token overlap between windows.
        page_number:   Page this text came from.
        heading:       Section heading to carry forward.
        start_idx:     Index offset for generating unique chunk IDs.

    Returns:
        List of ChunkRecord dicts.
    """
    words = text.split()
    max_words = int(max_tokens * _WORDS_PER_TOKEN)
    overlap_words = int(overlap_tokens * _WORDS_PER_TOKEN)

    if len(words) <= max_words:
        chunk_text = text.strip()
        if chunk_text:
            return [
                {
                    "chunk_id": _make_chunk_id(chunk_text, page_number, start_idx),
                    "page_number": page_number,
                    "section_heading": heading,
                    "text": chunk_text,
                }
            ]
        return []

    chunks: List[ChunkRecord] = []
    pos = 0
    local_idx = 0

    while pos < len(words):
        window_words = words[pos : pos + max_words]
        chunk_text = " ".join(window_words).strip()
        if chunk_text:
            chunks.append(
                {
                    "chunk_id": _make_chunk_id(
                        chunk_text, page_number, start_idx + local_idx
                    ),
                    "page_number": page_number,
                    "section_heading": heading,
                    "text": chunk_text,
                }
            )
        local_idx += 1
        step = max_words - overlap_words
        if step <= 0:
            step = max_words
        pos += step

    return chunks


def chunk_pages(
    pages: List[ReportPage],
    max_chunk_tokens: int = 600,
    overlap_tokens: int = 80,
    min_chunk_tokens: int = 50,
    prefer_section_boundaries: bool = True,
) -> List[ChunkRecord]:
    """
    Convert a list of ReportPage records into ChunkRecord records.

    Args:
        pages:                    Extracted PDF pages.
        max_chunk_tokens:         Approximate max token count per chunk.
        overlap_tokens:           Token overlap for sliding windows.
        min_chunk_tokens:         Discard chunks smaller than this.
        prefer_section_boundaries: Group pages by heading when possible.

    Returns:
        List of ChunkRecord dicts.
    """
    if not pages:
        logger.warning("No pages provided to chunker.")
        return []

    all_chunks: List[ChunkRecord] = []
    chunk_counter = 0

    if prefer_section_boundaries:
        # --- Group consecutive pages by heading ---
        groups: List[dict] = []  # {heading, pages: List[ReportPage]}
        current_heading: str = ""
        current_group: List[ReportPage] = []

        for page in pages:
            h = page.get("section_heading", "") or ""
            if h and h != current_heading and current_group:
                groups.append(
                    {"heading": current_heading, "pages": list(current_group)}
                )
                current_group = []
                current_heading = h
            elif h and not current_group:
                current_heading = h
            current_group.append(page)

        if current_group:
            groups.append({"heading": current_heading, "pages": current_group})

        for group in groups:
            heading = group["heading"] or "Unknown Section"
            group_pages = group["pages"]
            start_page = group_pages[0]["page_number"]

            combined_text = "\n\n".join(
                p["text"] for p in group_pages if p.get("text", "").strip()
            )

            if not combined_text.strip():
                continue

            windows = _split_into_windows(
                combined_text,
                max_chunk_tokens,
                overlap_tokens,
                start_page,
                heading,
                chunk_counter,
            )

            for w in windows:
                if _approx_tokens(w["text"]) >= min_chunk_tokens:
                    all_chunks.append(w)
                    chunk_counter += 1
                else:
                    logger.debug(
                        "Discarding undersized chunk from page %d (< %d tokens)",
                        w["page_number"],
                        min_chunk_tokens,
                    )

    else:
        # --- Page-by-page sliding window fallback ---
        for page in pages:
            text = page.get("text", "").strip()
            if not text:
                continue
            heading = page.get("section_heading", "") or f"Page {page['page_number']}"
            windows = _split_into_windows(
                text,
                max_chunk_tokens,
                overlap_tokens,
                page["page_number"],
                heading,
                chunk_counter,
            )
            for w in windows:
                if _approx_tokens(w["text"]) >= min_chunk_tokens:
                    all_chunks.append(w)
                    chunk_counter += 1

    logger.info(
        "Chunking complete: %d pages → %d chunks", len(pages), len(all_chunks)
    )
    return all_chunks
