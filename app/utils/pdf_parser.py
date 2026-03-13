"""
PDF ingestion module.

Extracts text page-by-page from a local PDF using PyMuPDF (fitz).
Attempts heuristic heading detection based on font size.

Phase 2 TODO:
    - Table extraction using fitz's table support or pdfplumber
    - OCR fallback for scanned pages
    - Multi-column layout handling
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from app.schemas.state import ReportPage
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Minimum characters for a page to be considered non-empty
MIN_PAGE_CHARS = 30

# Heuristics for heading detection
HEADING_MAX_WORDS = 15       # headings are usually short
HEADING_MIN_FONT_RATIO = 1.1 # heading font >= this * body median font


def _detect_heading_from_blocks(blocks: list) -> Optional[str]:
    """
    Attempt to identify a section heading from raw PyMuPDF text blocks.

    Strategy:
    1. Compute the median font size across all spans.
    2. If the first block(s) use a larger font and are short, treat as heading.
    3. Fall back to all-caps or title-case short lines at the top.

    Returns the heading string or None.
    """
    # Collect all (font_size, text) tuples from spans
    all_spans: List[Tuple[float, str]] = []
    for block in blocks:
        if block.get("type") != 0:  # 0 = text block
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                txt = span.get("text", "").strip()
                size = span.get("size", 0.0)
                if txt:
                    all_spans.append((size, txt))

    if not all_spans:
        return None

    sizes = [s for s, _ in all_spans]
    median_size = sorted(sizes)[len(sizes) // 2]

    # Gather leading spans that are larger than median
    heading_parts: List[str] = []
    for size, text in all_spans[:10]:  # inspect first ~10 spans
        word_count = len(text.split())
        if (
            size >= median_size * HEADING_MIN_FONT_RATIO
            and word_count <= HEADING_MAX_WORDS
        ):
            heading_parts.append(text)
        else:
            break  # stop at first normal-sized span

    if heading_parts:
        return " ".join(heading_parts)

    # Fallback: look for ALL-CAPS short line at start of page
    for _, text in all_spans[:5]:
        clean = text.strip()
        if (
            clean.isupper()
            and 2 <= len(clean.split()) <= HEADING_MAX_WORDS
            and len(clean) > 3
        ):
            return clean

    return None


def _clean_text(raw: str) -> str:
    """Normalise whitespace in extracted text."""
    # Replace multiple newlines with double newline (paragraph separator)
    text = re.sub(r"\n{3,}", "\n\n", raw)
    # Replace tabs with spaces
    text = text.replace("\t", " ")
    # Collapse repeated spaces (but keep newlines)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


def parse_pdf(pdf_path: str) -> List[ReportPage]:
    """
    Extract pages from a PDF file.

    Args:
        pdf_path: Absolute or relative path to the PDF.

    Returns:
        List of ReportPage dicts, one per page (including empty pages).

    Raises:
        FileNotFoundError: If the PDF does not exist.
        RuntimeError: If PyMuPDF cannot open the file.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF is required: pip install pymupdf"
        ) from exc

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info("Opening PDF: %s", path.name)

    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise RuntimeError(f"Cannot open PDF '{pdf_path}': {exc}") from exc

    pages: List[ReportPage] = []
    empty_pages: List[int] = []

    for page_index in range(len(doc)):
        page_number = page_index + 1  # 1-based
        try:
            page = doc[page_index]

            # Extract raw text
            raw_text = page.get_text("text")
            clean = _clean_text(raw_text)

            # Attempt heading detection using block-level data
            heading: Optional[str] = None
            try:
                block_data = page.get_text("dict")
                heading = _detect_heading_from_blocks(block_data.get("blocks", []))
            except Exception as heading_err:
                logger.debug(
                    "Heading detection failed on page %d: %s", page_number, heading_err
                )

            if len(clean) < MIN_PAGE_CHARS:
                empty_pages.append(page_number)
                logger.debug(
                    "Page %d has very little text (%d chars) — logged but kept",
                    page_number,
                    len(clean),
                )

            record: ReportPage = {
                "page_number": page_number,
                "text": clean,
            }
            if heading:
                record["section_heading"] = heading

            pages.append(record)

        except Exception as page_err:
            logger.warning(
                "Failed to extract page %d: %s", page_number, page_err
            )
            # Include an empty record so page numbers stay aligned
            pages.append(
                {
                    "page_number": page_number,
                    "text": "",
                }
            )

    doc.close()

    logger.info(
        "Extracted %d pages from '%s'. Empty/sparse: %s",
        len(pages),
        path.name,
        empty_pages if empty_pages else "none",
    )

    return pages
