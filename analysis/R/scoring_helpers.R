# R/scoring_helpers.R
# ─────────────────────────────────────────────────────────────────────────────
# Maturity index and derived metrics computed from pipeline evidence.
#
# The maturity_index is a company × year composite that captures:
#   A. Average computed_score (0–13 scale from the pipeline)
#   B. Stage composition (proportion at each implementation stage)
#   C. Quality rate (proportion with quantitative or oversight support)
#
# This is used in Chapter 4 for longitudinal theory testing.
# ─────────────────────────────────────────────────────────────────────────────

library(tidyverse)

# ── Stage weights (mirrors the pipeline scoring rubric) ───────────────────────

STAGE_WEIGHTS <- c(
  "mention_only"                         = 1,
  "planned_action"                       = 2,
  "implementation_in_progress"           = 3,
  "implemented_with_measurable_evidence" = 4
)

# ── Maturity index per company × year ─────────────────────────────────────────
#
# Formula:
#   maturity_index = (avg_score / 13) * 0.50        # score component (50%)
#                  + stage_weight_avg / 4  * 0.30   # stage component (30%)
#                  + quality_rate          * 0.20   # quality component (20%)
#
# Result is in [0, 1] — higher = more mature disclosure
#
compute_maturity_index <- function(ev_wide) {
  ev_wide |>
    group_by(company, report_year) |>
    summarise(
      n                 = n(),
      avg_score         = mean(computed_score, na.rm = TRUE),
      stage_weight_avg  = mean(STAGE_WEIGHTS[as.character(implementation_stage)],
                               na.rm = TRUE),
      quality_rate      = mean(quantitative_support | oversight_support,
                               na.rm = TRUE),
      quant_rate        = mean(quantitative_support, na.rm = TRUE),
      oversight_rate    = mean(oversight_support,    na.rm = TRUE),
      pct_weak          = mean(computed_strength == "weak",     na.rm = TRUE),
      pct_moderate      = mean(computed_strength == "moderate", na.rm = TRUE),
      pct_strong        = mean(computed_strength == "strong",   na.rm = TRUE),
      pct_mention_only  = mean(implementation_stage == "mention_only",                         na.rm = TRUE),
      pct_planned       = mean(implementation_stage == "planned_action",                       na.rm = TRUE),
      pct_in_progress   = mean(implementation_stage == "implementation_in_progress",           na.rm = TRUE),
      pct_measurable    = mean(implementation_stage == "implemented_with_measurable_evidence", na.rm = TRUE),
      .groups = "drop"
    ) |>
    mutate(
      maturity_index = (avg_score / 13)       * 0.50 +
                       (stage_weight_avg / 4)  * 0.30 +
                       quality_rate            * 0.20,
      period = if_else(report_year <= 2021,
                       "Annual (2016–2021)",
                       "Integrated (2022–2025)")
    )
}

# ── SDG-level maturity per company × year × SDG ───────────────────────────────

compute_sdg_maturity <- function(ev) {
  ev |>
    group_by(company, report_year, sdg) |>
    summarise(
      n              = n(),
      avg_score      = mean(computed_score, na.rm = TRUE),
      quality_rate   = mean(quantitative_support | oversight_support,
                            na.rm = TRUE),
      stage_weight   = mean(STAGE_WEIGHTS[as.character(implementation_stage)],
                            na.rm = TRUE),
      sdg_maturity   = (avg_score / 13) * 0.50 +
                       (stage_weight / 4) * 0.30 +
                       quality_rate * 0.20,
      .groups = "drop"
    ) |>
    mutate(
      sdg_num = as.integer(str_extract(as.character(sdg), "\\d+")),
      period  = if_else(report_year <= 2021,
                        "Annual (2016–2021)",
                        "Integrated (2022–2025)")
    )
}

# ── Period-level aggregates (for pre/post comparison in Ch4) ──────────────────

compute_period_summary <- function(ev_wide) {
  ev_wide |>
    mutate(period = if_else(report_year <= 2021,
                            "Annual (2016–2021)",
                            "Integrated (2022–2025)")) |>
    group_by(company, period) |>
    summarise(
      n_items        = n(),
      avg_score      = mean(computed_score,     na.rm = TRUE),
      quality_rate   = mean(quantitative_support | oversight_support, na.rm = TRUE),
      quant_rate     = mean(quantitative_support, na.rm = TRUE),
      oversight_rate = mean(oversight_support,    na.rm = TRUE),
      pct_measurable = mean(implementation_stage == "implemented_with_measurable_evidence",
                            na.rm = TRUE),
      pct_weak       = mean(computed_strength == "weak",   na.rm = TRUE),
      pct_strong     = mean(computed_strength == "strong", na.rm = TRUE),
      .groups = "drop"
    )
}

# ── Tag-level co-occurrence matrix (for network analysis) ─────────────────────

build_sdg_tag_matrix <- function(ev, weight_by = c("count", "score")) {
  weight_by <- match.arg(weight_by)

  # Unnest tags
  ev_tags <- ev |>
    unnest(evidence_tags) |>
    rename(tag = evidence_tags)

  if (weight_by == "count") {
    ev_tags |>
      count(sdg, tag) |>
      rename(weight = n)
  } else {
    ev_tags |>
      group_by(sdg, tag) |>
      summarise(weight = mean(computed_score, na.rm = TRUE), .groups = "drop")
  }
}

# ── SDG co-occurrence matrix (which SDGs appear together) ─────────────────────

build_sdg_cooccurrence <- function(ev_wide) {
  # Items with multiple candidate_sdgs: create pairwise links
  multi_sdg <- ev_wide |>
    filter(map_int(candidate_sdgs, length) > 1) |>
    select(evidence_id, candidate_sdgs)

  if (nrow(multi_sdg) == 0) return(tibble(from = character(), to = character(), n = integer()))

  multi_sdg |>
    mutate(pairs = map(candidate_sdgs, function(sdgs) {
      if (length(sdgs) < 2) return(tibble(from = character(), to = character()))
      combn(sort(sdgs), 2, simplify = FALSE) |>
        map_dfr(~tibble(from = .x[1], to = .x[2]))
    })) |>
    select(pairs) |>
    unnest(pairs) |>
    count(from, to, name = "n")
}
