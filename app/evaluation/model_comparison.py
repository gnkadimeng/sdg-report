"""
Model comparison runner.

Runs the benchmark against multiple chat model / embedding model combinations
and produces a comparison report.

Selection criteria (in priority order):
    1. Lowest over-claim rate
    2. Best extraction accuracy (SDG Jaccard + tag Jaccard mean)
    3. Acceptable runtime (per-item average)

Usage (CLI):
    python main.py compare \
        --benchmark data/benchmarks/example_benchmark.jsonl \
        --models mistral llama3.2 \
        --output-dir data/outputs/model_comparison
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.evaluation.benchmark import load_benchmark, evaluate_item
from app.evaluation.metrics import compute_aggregate_metrics
from app.extraction.extractor import EvidenceExtractor
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _score_model(agg: Dict[str, Any]) -> float:
    """
    Composite selection score (higher is better).

    Formula:
        score = (1 - over_claim_rate) * 2
              + sdg_jaccard_mean
              + tag_jaccard_mean
              + stage_exact_rate
              + quant_exact_rate
              + oversight_exact_rate
    """
    return (
        (1.0 - agg.get("over_claim_rate", 1.0)) * 2.0
        + agg.get("sdg_jaccard_mean", 0.0)
        + agg.get("tag_jaccard_mean", 0.0)
        + agg.get("stage_exact_rate", 0.0)
        + agg.get("quant_exact_rate", 0.0)
        + agg.get("oversight_exact_rate", 0.0)
    )


def compare_models(
    benchmark_path: str,
    chat_models: List[str],
    embedding_models: List[str],
    output_dir: str,
    base_url: str = "http://localhost:11434",
    max_retries: int = 3,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """
    Run benchmark for each (chat_model × embedding_model) combination.

    Args:
        benchmark_path:   Path to benchmark JSONL.
        chat_models:      List of Ollama chat model names.
        embedding_models: List of Ollama embedding model names.
        output_dir:       Directory for output files.
        base_url:         Ollama server URL.
        max_retries:      JSON retry count.
        temperature:      Model temperature.

    Returns:
        Comparison results dict including recommended model combination.
    """
    items = load_benchmark(benchmark_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    comparison_results = []

    for chat_model in chat_models:
        for embed_model in embedding_models:
            combo_key = f"{chat_model}+{embed_model}"
            logger.info("Comparing combo: %s", combo_key)

            extractor = EvidenceExtractor(
                model=chat_model,
                base_url=base_url,
                max_retries=max_retries,
                temperature=temperature,
            )

            t_start = time.time()
            results = []
            for item in items:
                result = evaluate_item(item, extractor)
                results.append(result)
            total_time = round(time.time() - t_start, 2)

            aggregate = compute_aggregate_metrics(results)
            avg_runtime = round(
                sum(r.get("runtime_seconds", 0) for r in results) / len(results)
                if results else 0.0,
                2,
            )

            combo_result = {
                "chat_model": chat_model,
                "embedding_model": embed_model,
                "combo_key": combo_key,
                "total_runtime_seconds": total_time,
                "avg_item_runtime_seconds": avg_runtime,
                "retrieved_chunk_count": None,  # N/A for benchmark (no retrieval)
                "extracted_evidence_count": sum(r.get("extracted_count", 0) for r in results),
                "valid_evidence_count": sum(r.get("valid_count", 0) for r in results),
                "aggregate_metrics": aggregate,
                "selection_score": round(_score_model(aggregate), 4),
            }
            comparison_results.append(combo_result)
            logger.info(
                "  over_claim_rate=%.3f  sdg_jaccard=%.3f  selection_score=%.3f",
                aggregate.get("over_claim_rate", 0),
                aggregate.get("sdg_jaccard_mean", 0),
                combo_result["selection_score"],
            )

    # Rank by selection score (descending)
    comparison_results.sort(key=lambda x: x["selection_score"], reverse=True)
    recommended = comparison_results[0] if comparison_results else None

    output = {
        "run_at": datetime.now().isoformat(),
        "benchmark": benchmark_path,
        "recommended": recommended,
        "ranked_results": comparison_results,
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"model_comparison_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    _write_comparison_report(out_dir / f"model_comparison_{ts}.md", output)

    logger.info(
        "Model comparison complete. Recommended: %s (score=%.3f). Output: %s",
        recommended["combo_key"] if recommended else "none",
        recommended["selection_score"] if recommended else 0,
        json_path,
    )

    return output


def _write_comparison_report(path: Path, output: Dict[str, Any]) -> None:
    lines = [
        "# SDG Extractor — Model Comparison Report",
        f"**Run at:** {output['run_at']}",
        f"**Benchmark:** {output['benchmark']}",
        "",
    ]

    rec = output.get("recommended")
    if rec:
        lines += [
            "## Recommended Combination",
            "",
            f"**{rec['combo_key']}**",
            f"- Selection score: {rec['selection_score']}",
            f"- Over-claim rate: {rec['aggregate_metrics'].get('over_claim_rate', 'N/A')}",
            f"- SDG Jaccard mean: {rec['aggregate_metrics'].get('sdg_jaccard_mean', 'N/A')}",
            f"- Avg item runtime: {rec['avg_item_runtime_seconds']}s",
            "",
        ]

    lines += [
        "## All Combinations (ranked)",
        "",
        "| Rank | Combo | Select Score | Over-claim | SDG Jaccard | Stage Exact | Avg RT |",
        "|------|-------|-------------|------------|-------------|-------------|--------|",
    ]

    for rank, r in enumerate(output.get("ranked_results", []), 1):
        agg = r["aggregate_metrics"]
        lines.append(
            f"| {rank} | {r['combo_key']} "
            f"| {r['selection_score']} "
            f"| {agg.get('over_claim_rate', 'N/A')} "
            f"| {agg.get('sdg_jaccard_mean', 'N/A')} "
            f"| {agg.get('stage_exact_rate', 'N/A')} "
            f"| {r['avg_item_runtime_seconds']}s |"
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
