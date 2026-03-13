#!/usr/bin/env bash
# Monitor SDG pipeline progress — all companies.
# Usage: ./monitor.sh

OUTPUTS="data/outputs"
PY=".venv/bin/python3.11"

count_evidence() {
  local folder="$1" field="$2"
  $PY -c "
import json; d=json.load(open('$folder/evidence.json'))
print(len(d.get('$field',[])))
" 2>/dev/null || echo "?"
}

show_section() {
  # Args: company label logfile "year:name" "year:name" ...
  local company="$1" label="$2" logfile="$3"
  shift 3
  local reports=("$@")
  local total="${#reports[@]}"
  local done_count=0 total_valid=0

  echo ""
  echo "  ── $label $(printf '%0.s─' {1..50})"
  printf "  %-6s %-40s %-10s %-7s %-7s\n" "YEAR" "REPORT" "STATUS" "VALID" "REJ"
  echo "  $(printf '%0.s-' {1..74})"

  for entry in "${reports[@]}"; do
    year="${entry%%:*}"
    name="${entry#*:}"
    folder=$(ls -dt "$OUTPUTS/${company}_${year}_"* 2>/dev/null | head -1)

    if [[ -n "$folder" && -f "$folder/evidence.json" ]]; then
      valid=$(count_evidence "$folder" "validated_evidence")
      rejected=$(count_evidence "$folder" "rejected_evidence")
      status="DONE"
      done_count=$((done_count + 1))
      [[ "$valid" =~ ^[0-9]+$ ]] && total_valid=$((total_valid + valid))
    elif [[ -f "$logfile" ]] && tail -30 "$logfile" 2>/dev/null | grep -q "$year"; then
      status="RUNNING"; valid="-"; rejected="-"
    else
      status="pending"; valid="-"; rejected="-"
    fi

    if   [[ "$status" == "DONE"    ]]; then col="\033[32m"; rst="\033[0m"
    elif [[ "$status" == "RUNNING" ]]; then col="\033[33m"; rst="\033[0m"
    else                                    col="\033[90m"; rst="\033[0m"; fi

    printf "  %-6s %-40s ${col}%-10s${rst} %-7s %-7s\n" \
      "$year" "${name:0:40}" "$status" "$valid" "$rejected"
  done

  echo "  $(printf '%0.s-' {1..74})"
  printf "  Completed: %d/%d    Total valid evidence: %d\n" "$done_count" "$total" "$total_valid"
  if [[ -f "$logfile" ]]; then
    last=$(tail -1 "$logfile" 2>/dev/null)
    [[ -n "$last" ]] && printf "  Log: %.70s\n" "$last"
  fi
}

clear
while true; do
  tput cup 0 0 2>/dev/null || clear
  echo "========================================"
  echo "  SDG Batch Run Monitor"
  echo "  $(date '+%Y-%m-%d %H:%M:%S')"
  echo "========================================"

  show_section "coromandel" "Coromandel" "data/outputs/batch_run.log" \
    "2016:Annual Report 2015-16" \
    "2017:Annual Report 2016-17" \
    "2018:Annual Report 2017-18" \
    "2019:Annual Report 2018-19" \
    "2020:Annual Report 2019-20" \
    "2021:Annual Report 2020-21" \
    "2022:Integrated Annual Report 2021-22" \
    "2023:Integrated Annual Report 2022-23" \
    "2024:Integrated Annual Report 2023-24" \
    "2025:Integrated Annual Report 2024-25"

  show_section "jswsteel" "JSW Steel" "data/outputs/jswsteel_run.log" \
    "2020:Integrated Report FY 2019-20" \
    "2022:BRSR 2021-22" \
    "2023:Integrated Report + BRSR FY 2022-23" \
    "2024:Integrated Annual Report FY 2023-24" \
    "2025:Integrated Annual Report FY 2024-25"

  echo ""
  echo "  Refreshing every 15s — Ctrl+C to exit"
  sleep 15
done
