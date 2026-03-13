"""
Benchmark runner for the SDG evidence extraction pipeline.

Benchmark format (JSONL):
    One JSON object per line, each representing one evaluation item.
    See data/benchmarks/example_benchmark.jsonl for format.

The runner:
    1. Loads benchmark items from a JSONL file
    2. For each item, creates a synthetic single-chunk pipeline run
       (bypasses PDF ingestion — directly uses chunk_text)
    3. Runs extraction + validation + scoring nodes
    4. Computes per-item metrics
    5. Writes results to JSON, CSV, and markdown scorecard

Note: This runner does NOT re-run PDF ingestion for benchmark items.
Benchmark items are text-only. This allows fast, reproducible evaluation.
"""

from __future__ import annotations

import csv
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.evaluation.metrics import (
    compute_aggregate_metrics,
    evidence_tag_accuracy,
    is_oversight_overclaim,
    is_quantitative_overclaim,
    is_stage_overclaim,
    oversight_support_accuracy,
    quantitative_support_accuracy,
    sdg_set_overlap_accuracy,
    implementation_stage_accuracy,
    validation_pass_accuracy,
)
from app.extraction.extractor import EvidenceExtractor
from app.nodes.score_evidence import _compute_score
from app.nodes.validate_evidence import _validate_record
from app.schemas.state import ChunkRecord, EvidenceRecord
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Benchmark item loading
# ---------------------------------------------------------------------------


def load_benchmark(jsonl_path: str) -> List[Dict[str, Any]]:
    """
    Load benchmark items from a JSONL file.

    Args:
        jsonl_path: Path to the benchmark JSONL file.

    Returns:
        List of benchmark item dicts.
    """
    path = Path(jsonl_path)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {jsonl_path}")

    items = []
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                item = json.loads(line)
                items.append(item)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping malformed benchmark line %d: %s", line_num, exc
                )
    logger.info("Loaded %d benchmark items from '%s'.", len(items), jsonl_path)
    return items


# ---------------------------------------------------------------------------
# Single-item evaluation
# ---------------------------------------------------------------------------


def evaluate_item(
    item: Dict[str, Any],
    extractor: EvidenceExtractor,
) -> Dict[str, Any]:
    """
    Run extraction, validation, and scoring on a single benchmark item.

    Returns a dict containing:
        - benchmark item fields
        - extracted evidence (list)
        - per-item metrics
        - runtime
    """
    chunk: ChunkRecord = {
        "chunk_id": f"bench_{uuid.uuid4().hex[:8]}",
        "page_number": item.get("page_number", 1),
        "section_heading": item.get("section_heading", "Benchmark Section"),
        "text": item["chunk_text"],
    }

    company = item.get("company", "BenchmarkCo")
    report_name = item.get("report_name", "Benchmark Report")
    report_year = item.get("report_year", 2023)

    t0 = time.time()
    try:
        extracted = extractor.extract(
            chunk=chunk,
            company=company,
            report_name=report_name,
            report_year=report_year,
        )
    except Exception as exc:
        logger.error("Extraction failed for benchmark item: %s", exc)
        extracted = []
    runtime = round(time.time() - t0, 2)

    # Validate and score each extracted item
    scored_evidence = []
    for record in extracted:
        val_errors = _validate_record(record)
        if val_errors:
            record = {**record, "validation_status": "rejected", "validation_errors": val_errors}
        else:
            record = {**record, "validation_status": "valid", "validation_errors": []}
            raw_score, strength = _compute_score(record)
            record = {**record, "computed_score": raw_score, "computed_strength": strength}
        scored_evidence.append(record)

    # Select best evidence item for metric comparison (highest score or first valid)
    best: Optional[EvidenceRecord] = None
    valid_items = [e for e in scored_evidence if e.get("validation_status") == "valid"]
    if valid_items:
        best = max(valid_items, key=lambda e: e.get("computed_score", 0))

    # Compute metrics
    expected_sdgs = item.get("expected_sdgs", [])
    expected_tags = item.get("expected_evidence_tags", [])
    expected_stage = item.get("expected_implementation_stage", "")
    expected_quant = item.get("expected_quantitative_support", False)
    expected_oversight = item.get("expected_oversight_support", False)
    expected_valid = item.get("expected_valid", True)

    if best:
        pred_sdgs = best.get("candidate_sdgs", [])
        pred_tags = best.get("evidence_tags", [])
        pred_stage = best.get("implementation_stage", "")
        pred_quant = best.get("quantitative_support", False)
        pred_oversight = best.get("oversight_support", False)
        pred_valid = best.get("validation_status") == "valid"
        evidence_text = best.get("evidence_text", "")
    else:
        # No evidence extracted — treat as empty prediction
        pred_sdgs, pred_tags, pred_stage = [], [], ""
        pred_quant, pred_oversight, pred_valid = False, False, False
        evidence_text = ""

    metrics = {
        "sdg_jaccard": sdg_set_overlap_accuracy(pred_sdgs, expected_sdgs),
        "tag_jaccard": evidence_tag_accuracy(pred_tags, expected_tags),
        "stage_exact": implementation_stage_accuracy(pred_stage, expected_stage),
        "stage_overclaim": is_stage_overclaim(pred_stage, expected_stage) if pred_stage and expected_stage else False,
        "quant_exact": quantitative_support_accuracy(pred_quant, expected_quant),
        "oversight_exact": oversight_support_accuracy(pred_oversight, expected_oversight),
        "validation_correct": pred_valid == expected_valid,
        "quant_overclaim": is_quantitative_overclaim(evidence_text, pred_quant),
        "oversight_overclaim": is_oversight_overclaim(evidence_text, pred_oversight),
    }

    return {
        "item_id": item.get("notes", f"item_{uuid.uuid4().hex[:6]}"),
        "company": company,
        "report_name": report_name,
        "page_number": item.get("page_number", 1),
        "chunk_text_preview": item["chunk_text"][:100],
        "expected_sdgs": expected_sdgs,
        "expected_tags": expected_tags,
        "expected_stage": expected_stage,
        "expected_quant": expected_quant,
        "expected_oversight": expected_oversight,
        "expected_valid": expected_valid,
        "predicted_sdgs": pred_sdgs,
        "predicted_tags": pred_tags,
        "predicted_stage": pred_stage,
        "predicted_quant": pred_quant,
        "predicted_oversight": pred_oversight,
        "predicted_valid": pred_valid,
        "extracted_count": len(extracted),
        "valid_count": len(valid_items),
        "runtime_seconds": runtime,
        **metrics,
    }


# ---------------------------------------------------------------------------
# Full benchmark run
# ---------------------------------------------------------------------------


def run_benchmark(
    jsonl_path: str,
    output_dir: str,
    chat_model: str = "mistral",
    embedding_model: str = "nomic-embed-text",
    base_url: str = "http://localhost:11434",
    max_retries: int = 3,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """
    Run the full evaluation benchmark and write results.

    Args:
        jsonl_path:      Path to benchmark JSONL file.
        output_dir:      Directory to write results.
        chat_model:      Ollama chat model name.
        embedding_model: Ollama embedding model name (for logging).
        base_url:        Ollama server URL.
        max_retries:     Retries for JSON parse failures.
        temperature:     Model temperature.

    Returns:
        Dict containing all results and aggregate metrics.
    """
    items = load_benchmark(jsonl_path)

    extractor = EvidenceExtractor(
        model=chat_model,
        base_url=base_url,
        max_retries=max_retries,
        temperature=temperature,
    )

    results = []
    for i, item in enumerate(items):
        logger.info(
            "Evaluating item %d/%d: '%s'",
            i + 1,
            len(items),
            item.get("notes", "?"),
        )
        result = evaluate_item(item, extractor)
        results.append(result)

    aggregate = compute_aggregate_metrics(results)

    # Write outputs
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON results
    json_path = out_dir / f"eval_{chat_model.replace(':', '_')}_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model": chat_model,
                "embedding_model": embedding_model,
                "run_at": datetime.now().isoformat(),
                "aggregate": aggregate,
                "results": results,
            },
            f,
            indent=2,
        )
    logger.info("Evaluation JSON: %s", json_path)

    # CSV summary
    csv_path = out_dir / f"eval_{chat_model.replace(':', '_')}_{ts}.csv"
    if results:
        fieldnames = list(results[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in results:
                row = {
                    k: (
                        " | ".join(v) if isinstance(v, list) else v
                    )
                    for k, v in r.items()
                }
                writer.writerow(row)
    logger.info("Evaluation CSV: %s", csv_path)

    # Markdown scorecard
    md_path = out_dir / f"eval_{chat_model.replace(':', '_')}_{ts}.md"
    _write_scorecard(md_path, chat_model, embedding_model, aggregate, results)
    logger.info("Evaluation scorecard: %s", md_path)

    return {"aggregate": aggregate, "results": results, "output_dir": str(out_dir)}


def _write_scorecard(
    path: Path,
    chat_model: str,
    embedding_model: str,
    aggregate: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> None:
    lines = [
        f"# SDG Extractor Evaluation Scorecard",
        f"**Chat model:** `{chat_model}`  |  **Embedding model:** `{embedding_model}`",
        f"**Run at:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Items evaluated:** {aggregate.get('n', 0)}",
        "",
        "## Aggregate Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]
    for k, v in aggregate.items():
        if k == "n":
            continue
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## Per-Item Results",
        "",
        "| Item | SDG Jaccard | Tag Jaccard | Stage Match | Over-claim |",
        "|------|-------------|-------------|-------------|------------|",
    ]
    for r in results:
        overclaim = any([
            r.get("stage_overclaim"),
            r.get("quant_overclaim"),
            r.get("oversight_overclaim"),
        ])
        lines.append(
            f"| {r['item_id'][:40]} "
            f"| {r.get('sdg_jaccard', 0):.2f} "
            f"| {r.get('tag_jaccard', 0):.2f} "
            f"| {'✓' if r.get('stage_exact') else '✗'} "
            f"| {'⚠ YES' if overclaim else 'no'} |"
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
