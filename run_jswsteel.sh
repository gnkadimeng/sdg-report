#!/usr/bin/env bash
# run_jswsteel.sh — Run the SDG evidence pipeline on all JSW Steel reports

set -e
PYTHON=".venv/bin/python3.11"
BASE="data/raw_reports/jswsteel"
LOG="data/outputs/jswsteel_run.log"

mkdir -p data/outputs
> "$LOG"

run_report() {
  local pdf="$1" year="$2" name="$3"
  echo "" | tee -a "$LOG"
  echo "────────────────────────────────────" | tee -a "$LOG"
  echo "[$year] $name" | tee -a "$LOG"
  echo "  PDF: $BASE/$pdf" | tee -a "$LOG"
  echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG"
  $PYTHON main.py run \
    --pdf "$BASE/$pdf" \
    --company jswsteel \
    --report-name "$name" \
    --report-year "$year" \
    --output-dir data/outputs \
    2>&1 | tee -a "$LOG"
  echo "  Finished: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG"
  echo "[$year] DONE" | tee -a "$LOG"
}

echo "=== JSW Steel batch run — $(date '+%Y-%m-%d %H:%M:%S') ===" | tee -a "$LOG"

run_report "JSW Steel_IR2020_Final.pdf"                            2020 "Integrated Report FY 2019-20"
run_report "Business Responsiblity and Sustainability Report.pdf"  2022 "Business Responsibility and Sustainability Report 2021-22"
run_report "JSW- Steel-23-IR-BRSR-14-08-23.pdf"                   2023 "Integrated Report and BRSR FY 2022-23"
run_report "Integrated-Annual-Report-FY-2023-24.pdf"              2024 "Integrated Annual Report FY 2023-24"
run_report "Integrated-Annual-Report-FY-2024-25.pdf"              2025 "Integrated Annual Report FY 2024-25"

echo "" | tee -a "$LOG"
echo "=== All JSW Steel reports complete — $(date '+%Y-%m-%d %H:%M:%S') ===" | tee -a "$LOG"
