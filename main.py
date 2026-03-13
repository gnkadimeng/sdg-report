"""
SDG Evidence Extractor — CLI entry point.

Usage:
    # Run the full pipeline on a PDF
    python main.py run \
        --pdf data/raw_reports/my_report.pdf \
        --company "AgroCo" \
        --report-name "Sustainability Report 2023" \
        --report-year 2023

    # Run evaluation benchmark
    python main.py eval \
        --benchmark data/benchmarks/example_benchmark.jsonl \
        --output-dir data/outputs/eval

    # Compare models
    python main.py compare \
        --benchmark data/benchmarks/example_benchmark.jsonl \
        --models mistral llama3.2 \
        --output-dir data/outputs/comparison

    # Run unit tests
    pytest tests/ -v
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def _load_config(config_path: str) -> dict:
    """Load YAML config file, returning empty dict on error."""
    try:
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"[warning] Could not load config '{config_path}': {exc}")
        return {}


def _build_pipeline_config(args, cfg: dict) -> dict:
    """Merge YAML config + CLI args into a LangGraph configurable dict."""
    ollama = cfg.get("ollama", {})
    chunking = cfg.get("chunking", {})
    retrieval = cfg.get("retrieval", {})
    extraction = cfg.get("extraction", {})

    return {
        # Models
        "chat_model": getattr(args, "model", None) or ollama.get("chat_model", "mistral"),
        "embedding_model": getattr(args, "embedding_model", None) or ollama.get("embedding_model", "nomic-embed-text"),
        "base_url": ollama.get("base_url", "http://localhost:11434"),
        "chat_timeout": ollama.get("chat_timeout", 120),
        "embedding_timeout": ollama.get("embedding_timeout", 60),
        "max_retries": ollama.get("max_retries", 3),
        # Chunking
        "max_chunk_tokens": chunking.get("max_chunk_tokens", 600),
        "overlap_tokens": chunking.get("overlap_tokens", 80),
        "min_chunk_tokens": chunking.get("min_chunk_tokens", 50),
        "prefer_section_boundaries": chunking.get("prefer_section_boundaries", True),
        # Retrieval
        "top_k": retrieval.get("top_k", 20),
        "semantic_weight": retrieval.get("semantic_weight", 0.6),
        "keyword_weight": retrieval.get("keyword_weight", 0.4),
        "boilerplate_penalty": retrieval.get("boilerplate_penalty", 0.3),
        "min_retrieval_score": retrieval.get("min_retrieval_score", 0.15),
        # Extraction
        "temperature": extraction.get("temperature", 0.0),
        "max_evidence_per_chunk": extraction.get("max_evidence_per_chunk", 5),
    }


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


def cmd_run(args) -> int:
    """Run the full pipeline on a PDF report."""
    from app.utils.logger import configure_logging, get_logger

    cfg = _load_config(args.config)
    log_cfg = cfg.get("logging", {})
    configure_logging(
        level=log_cfg.get("level", "INFO"),
        log_file=log_cfg.get("log_file"),
    )
    logger = get_logger("main")

    # Validate inputs
    if not Path(args.pdf).exists():
        print(f"ERROR: PDF not found: {args.pdf}")
        return 1

    output_dir = args.output_dir or cfg.get("output", {}).get("output_dir", "data/outputs")

    pipeline_config = _build_pipeline_config(args, cfg)

    logger.info("Starting SDG evidence extraction pipeline…")

    try:
        from app.graph.pipeline import run_pipeline

        final_state = run_pipeline(
            pdf_path=args.pdf,
            company=args.company,
            report_name=args.report_name,
            report_year=args.report_year,
            output_dir=output_dir,
            config=pipeline_config,
        )
    except Exception as exc:
        print(f"Pipeline failed: {exc}")
        return 1

    # Print summary to stdout
    validated = final_state.get("validated_evidence", [])
    rejected = final_state.get("rejected_evidence", [])
    summaries = final_state.get("sdg_summaries", [])
    assessment = final_state.get("overall_assessment", "unknown")
    errors = final_state.get("errors", [])

    print("\n" + "=" * 60)
    print("  SDG EVIDENCE EXTRACTION COMPLETE")
    print("=" * 60)
    print(f"  Company:           {args.company}")
    print(f"  Report:            {args.report_name} ({args.report_year})")
    print(f"  Overall:           {assessment}")
    print(f"  Valid evidence:    {len(validated)}")
    print(f"  Rejected:          {len(rejected)}")
    print(f"  SDGs covered:      {len(summaries)}")
    if errors:
        print(f"  Pipeline errors:   {len(errors)}")
    print(f"\n  Outputs written to: {output_dir}/")
    print("=" * 60 + "\n")

    return 0


def cmd_eval(args) -> int:
    """Run the evaluation benchmark."""
    from app.utils.logger import configure_logging

    cfg = _load_config(args.config)
    log_cfg = cfg.get("logging", {})
    configure_logging(level=log_cfg.get("level", "INFO"))

    output_dir = args.output_dir or "data/outputs/eval"
    ollama = cfg.get("ollama", {})
    pipeline_cfg = _build_pipeline_config(args, cfg)

    try:
        from app.evaluation.benchmark import run_benchmark

        result = run_benchmark(
            jsonl_path=args.benchmark,
            output_dir=output_dir,
            chat_model=pipeline_cfg["chat_model"],
            embedding_model=pipeline_cfg["embedding_model"],
            base_url=pipeline_cfg["base_url"],
            max_retries=pipeline_cfg["max_retries"],
            temperature=pipeline_cfg["temperature"],
        )
    except Exception as exc:
        print(f"Evaluation failed: {exc}")
        return 1

    agg = result.get("aggregate", {})
    print("\n" + "=" * 60)
    print("  EVALUATION COMPLETE")
    print("=" * 60)
    for k, v in agg.items():
        print(f"  {k:<35} {v}")
    print(f"\n  Results written to: {output_dir}/")
    print("=" * 60 + "\n")
    return 0


def cmd_compare(args) -> int:
    """Compare multiple models on the benchmark."""
    from app.utils.logger import configure_logging

    cfg = _load_config(args.config)
    log_cfg = cfg.get("logging", {})
    configure_logging(level=log_cfg.get("level", "INFO"))

    output_dir = args.output_dir or "data/outputs/comparison"
    ollama = cfg.get("ollama", {})
    base_url = ollama.get("base_url", "http://localhost:11434")

    chat_models = args.models or cfg.get("model_comparison", {}).get(
        "chat_models", ["mistral", "llama3.2"]
    )
    embedding_models = args.embedding_models or cfg.get(
        "model_comparison", {}
    ).get("embedding_models", ["nomic-embed-text"])

    try:
        from app.evaluation.model_comparison import compare_models

        result = compare_models(
            benchmark_path=args.benchmark,
            chat_models=chat_models,
            embedding_models=embedding_models,
            output_dir=output_dir,
            base_url=base_url,
        )
    except Exception as exc:
        print(f"Model comparison failed: {exc}")
        return 1

    recommended = result.get("recommended", {})
    print("\n" + "=" * 60)
    print("  MODEL COMPARISON COMPLETE")
    print("=" * 60)
    if recommended:
        print(f"  Recommended:    {recommended.get('combo_key')}")
        print(f"  Select score:   {recommended.get('selection_score')}")
        agg = recommended.get("aggregate_metrics", {})
        print(f"  Over-claim:     {agg.get('over_claim_rate', 'N/A')}")
        print(f"  SDG Jaccard:    {agg.get('sdg_jaccard_mean', 'N/A')}")
    print(f"\n  Results written to: {output_dir}/")
    print("=" * 60 + "\n")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SDG Evidence Extractor — local-first SDG analysis from company reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- run ---
    run_p = sub.add_parser("run", help="Run pipeline on a PDF report")
    run_p.add_argument("--pdf", required=True, help="Path to the PDF report")
    run_p.add_argument("--company", required=True, help="Company name")
    run_p.add_argument(
        "--report-name", required=True, dest="report_name", help="Report title"
    )
    run_p.add_argument(
        "--report-year", required=True, type=int, dest="report_year",
        help="Report year (e.g. 2023)"
    )
    run_p.add_argument("--output-dir", dest="output_dir", help="Output directory")
    run_p.add_argument("--model", help="Override chat model (e.g. mistral)")
    run_p.add_argument(
        "--embedding-model", dest="embedding_model",
        help="Override embedding model (e.g. nomic-embed-text)"
    )

    # --- eval ---
    eval_p = sub.add_parser("eval", help="Run evaluation benchmark")
    eval_p.add_argument(
        "--benchmark",
        default="data/benchmarks/example_benchmark.jsonl",
        help="Path to benchmark JSONL",
    )
    eval_p.add_argument("--output-dir", dest="output_dir", help="Output directory")
    eval_p.add_argument("--model", help="Override chat model")
    eval_p.add_argument("--embedding-model", dest="embedding_model")

    # --- compare ---
    cmp_p = sub.add_parser("compare", help="Compare multiple models on benchmark")
    cmp_p.add_argument(
        "--benchmark",
        default="data/benchmarks/example_benchmark.jsonl",
        help="Path to benchmark JSONL",
    )
    cmp_p.add_argument(
        "--models",
        nargs="+",
        help="Chat models to compare (e.g. mistral llama3.2)",
    )
    cmp_p.add_argument(
        "--embedding-models",
        dest="embedding_models",
        nargs="+",
        help="Embedding models to compare",
    )
    cmp_p.add_argument("--output-dir", dest="output_dir", help="Output directory")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "run": cmd_run,
        "eval": cmd_eval,
        "compare": cmd_compare,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
