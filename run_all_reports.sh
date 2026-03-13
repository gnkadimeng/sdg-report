#!/usr/bin/env bash
# Run SDG evidence extraction pipeline on all Coromandel annual reports.
# Uses config.yaml defaults (gemma2 + nomic-embed-text).
# Runs sequentially — each report fully completes before the next starts.
#
# Usage:
#   chmod +x run_all_reports.sh
#   ./run_all_reports.sh
#
# Logs saved to: data/outputs/batch_run.log

set -euo pipefail

PYTHON=".venv/bin/python3.11"
LOGFILE="data/outputs/batch_run.log"
mkdir -p data/outputs

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOGFILE"
}

run_report() {
  local pdf="$1"
  local year="$2"
  local name="$3"

  log "START: $pdf (year=$year)"
  if "$PYTHON" main.py run \
    --pdf "$pdf" \
    --company "Coromandel" \
    --report-name "$name" \
    --report-year "$year" \
    2>&1 | tee -a "$LOGFILE"; then
    log "OK: $pdf"
  else
    log "FAILED: $pdf (exit $?)"
  fi
  echo "---" | tee -a "$LOGFILE"
}

log "=== Batch run started ==="

run_report "data/AnnualReport_2015_16.pdf"          2016 "Annual Report 2015-16"
run_report "data/AnnualReport_2016_17.pdf"          2017 "Annual Report 2016-17"
run_report "data/AnnualReport2017-2018.pdf"         2018 "Annual Report 2017-18"
run_report "data/AnnualReport2018-2019.pdf"         2019 "Annual Report 2018-19"
run_report "data/AR-20.pdf"                         2020 "Annual Report 2019-20"
run_report "data/AnnualReport2020-2021.pdf"         2021 "Annual Report 2020-21"
run_report "data/Integrated-Annual-Report-2021-22.pdf" 2022 "Integrated Annual Report 2021-22"
run_report "data/Integrated-Annual-Report-FY-2022-23.pdf" 2023 "Integrated Annual Report 2022-23"
run_report "data/Integrated-Annual-Report-FY-2023-24.pdf" 2024 "Integrated Annual Report 2023-24"
run_report "data/Integrated-Annual-Report-2024-25-1.pdf"  2025 "Integrated Annual Report 2024-25"

log "=== Batch run complete ==="
