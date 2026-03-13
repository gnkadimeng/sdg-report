# SDG Evidence Extractor

A local-first, conservative evidence-extraction system that analyses company sustainability reports for text-supported indicators of alignment with the UN Sustainable Development Goals (SDGs).

**Not a chatbot. Not a generic ESG summarizer.**

The system finds auditable text evidence, distinguishes weak rhetoric from stronger implementation evidence, and scores everything deterministically — no LLM judgment on strength.

---

## Design Principles

1. **LangGraph as a workflow, not an agent** — linear pipeline, no loops
2. **LLM for extraction and normalisation only** — structured JSON output, no free-form assessment
3. **Deterministic validation and scoring** — 100% rule-based in Python
4. **Conservative bias** — prefer false negatives over unsupported positive claims
5. **Every final evidence item includes a page citation**

---

## Architecture

```
PDF Report
    │
    ▼
ingest_pdf         ← PyMuPDF, page-by-page text + heuristic headings
    │
    ▼
chunk_document     ← Section-aware chunking with sliding-window fallback
    │
    ▼
retrieve_chunks    ← Hybrid: Ollama embeddings (cosine sim) + keyword scoring
    │                 + boilerplate down-ranking
    ▼
extract_evidence   ← Ollama chat → structured JSON extraction
    │                 (LLM only labels tags, stage, SDGs — no strength)
    ▼
validate_evidence  ← Deterministic Python: 8 validation rules
    │
    ▼
score_evidence     ← Deterministic scoring: maturity + tag bonuses + support
    │
    ▼
aggregate_findings ← Group by SDG, deterministic overall assessment
    │
    ▼
write_outputs      ← JSON + CSV + Markdown with page citations
```

### Scoring Formula (documented)

| Dimension | Value |
|-----------|-------|
| Action maturity: `mention_only` | 1 |
| Action maturity: `planned_action` | 2 |
| Action maturity: `implementation_in_progress` | 3 |
| Action maturity: `implemented_with_measurable_evidence` | 4 |
| Tag bonus: `policy`, `initiative`, `target`, `kpi` | +1 each |
| Tag bonus: `measured_outcome` | +2 |
| `quantitative_support == True` | +1 |
| `oversight_support == True` | +1 |
| **Maximum possible score** | **12** |

Strength labels: `weak` ≤2 / `moderate` 3–5 / `strong` ≥6

---

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) running locally
- Pull the models you intend to use:

```bash
ollama pull mistral
ollama pull nomic-embed-text
# Optional alternatives:
ollama pull llama3.2
```

---

## Installation

```bash
git clone <repo>
cd sdg-evidence-extractor

python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

---

## Usage

### Run the pipeline on a PDF

```bash
python main.py run \
  --pdf data/raw_reports/agroco_sustainability_2023.pdf \
  --company "AgroCo" \
  --report-name "Sustainability Report 2023" \
  --report-year 2023
```

Outputs are written to `data/outputs/<company>_<year>_<timestamp>/`:
- `evidence.json` — full structured output
- `evidence.csv` — flat evidence table
- `report.md` — human-readable markdown summary

### Override models

```bash
python main.py run \
  --pdf my_report.pdf \
  --company "AgroCo" \
  --report-name "Report 2023" \
  --report-year 2023 \
  --model llama3.2 \
  --embedding-model nomic-embed-text
```

### Run the evaluation benchmark

```bash
python main.py eval \
  --benchmark data/benchmarks/example_benchmark.jsonl \
  --output-dir data/outputs/eval
```

### Compare models

```bash
python main.py compare \
  --benchmark data/benchmarks/example_benchmark.jsonl \
  --models mistral llama3.2 \
  --output-dir data/outputs/comparison
```

### Run tests

```bash
pytest tests/ -v
```

Tests cover all validation rules and scoring formulas. No Ollama connection required.

---

## Configuration

Edit `config.yaml` to adjust models, thresholds, and output settings:

```yaml
ollama:
  chat_model: "mistral"
  embedding_model: "nomic-embed-text"

retrieval:
  top_k: 20
  semantic_weight: 0.6
  keyword_weight: 0.4
  boilerplate_penalty: 0.3

chunking:
  max_chunk_tokens: 600
  overlap_tokens: 80
```

---

## Project Structure

```
app/
  graph/            # LangGraph pipeline definition
  nodes/            # One node per pipeline stage
  retrieval/        # SDG lexicon, embeddings, hybrid retrieval
  extraction/       # LLM prompts + JSON extraction + retry logic
  evaluation/       # Benchmark runner, metrics, model comparison
  schemas/          # TypedDict state definitions
  utils/            # PDF parser, chunker, logger

data/
  raw_reports/      # Place PDF reports here
  benchmarks/       # Benchmark JSONL files
  outputs/          # Pipeline output (auto-created)

tests/
  test_scoring.py   # Unit tests for deterministic scoring
  test_validation.py # Unit tests for deterministic validation

main.py             # CLI entry point
config.yaml         # Configuration
pyproject.toml      # Dependencies
example_output.md   # Example markdown output layout
```

---

## Benchmark Format

Create your own benchmark JSONL. Each line is a JSON object:

```jsonl
{
  "company": "AgroCo",
  "report_name": "Sustainability Report 2023",
  "report_year": 2023,
  "page_number": 14,
  "section_heading": "Climate Action",
  "chunk_text": "We reduced Scope 1+2 emissions by 18%...",
  "expected_sdgs": ["SDG 13"],
  "expected_evidence_tags": ["measured_outcome", "kpi"],
  "expected_implementation_stage": "implemented_with_measurable_evidence",
  "expected_quantitative_support": true,
  "expected_oversight_support": false,
  "expected_valid": true,
  "notes": "positive_climate_evidence"
}
```

Include **both positive items** (should be extracted) and **negative items** (generic boilerplate that should return no evidence). See `data/benchmarks/example_benchmark.jsonl` for examples.

---

## Evaluation Metrics

| Metric | Description |
|--------|-------------|
| `sdg_jaccard_mean` | Jaccard similarity of predicted vs expected SDG sets |
| `tag_jaccard_mean` | Jaccard similarity of predicted vs expected evidence tags |
| `stage_exact_rate` | Fraction of exact implementation stage matches |
| `over_claim_rate` | Rate of unsupported positive classifications |
| `validation_accuracy` | Fraction of correct valid/rejected decisions |
| `quant_exact_rate` | Quantitative support exact match rate |
| `oversight_exact_rate` | Oversight support exact match rate |

**Over-claim** is defined as:
- Stage assigned stronger than the text supports
- `quantitative_support=True` with no numeric/metric pattern in text
- `oversight_support=True` with no board/committee wording in text

Model selection prioritises: lowest over-claim rate → best extraction accuracy → acceptable runtime.

---

## Known Limitations (Phase 2 Work)

- **Table extraction**: Tables in PDFs are not parsed (text-only MVP). Phase 2: `pdfplumber` or `fitz` table support.
- **Scanned PDFs**: No OCR fallback. Only digital-text PDFs are supported.
- **Multi-column layouts**: May produce garbled text. Phase 2: layout-aware extraction.
- **Heading detection**: Heuristic only (font size). Phase 2: bookmark-based structure extraction.
- **LangGraph checkpointing**: Not implemented. Phase 2: add `SqliteSaver` for resumable runs.
- **Parallel extraction**: Chunks are processed sequentially. Phase 2: async batch extraction.
- **Cross-report analysis**: One report per run. Phase 2: portfolio-level aggregation.

---

## Caveats

This tool produces automated evidence extraction from text. It:
- Does **not** provide audit opinions
- Does **not** verify company claims
- Does **not** assess real-world impact
- **Will miss evidence** in tables, figures, and scanned pages
- Produces false negatives by design (conservative bias)

Evidence strength reflects textual quality of disclosures, not actual sustainability performance.
