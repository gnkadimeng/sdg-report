#!/usr/bin/env bash
# Rerun the 4 reports that previously ran with mistral (wrong model).
# This will produce new output folders alongside the old ones.

set -euo pipefail

PYTHON=".venv/bin/python3.11"
LOGFILE="data/outputs/rerun.log"
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
    log "FAILED: $pdf"
  fi
  echo "---" | tee -a "$LOGFILE"
}

log "=== Rerun (gemma2) started ==="

run_report "data/AnnualReport_2015_16.pdf" 2016 "Annual Report 2015-16"
run_report "data/AnnualReport_2016_17.pdf" 2017 "Annual Report 2016-17"
run_report "data/AnnualReport2017-2018.pdf" 2018 "Annual Report 2017-18"
run_report "data/AnnualReport2018-2019.pdf" 2019 "Annual Report 2018-19"

log "=== Rerun complete ==="
