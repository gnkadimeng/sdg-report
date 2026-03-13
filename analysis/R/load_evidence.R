# R/load_evidence.R
# ─────────────────────────────────────────────────────────────────────────────
# Loads all evidence.json outputs from the Python pipeline into tidy tibbles.
#
# Strategy:
#   - For each company × year, find the LATEST output folder (lexicographic
#     sort on the timestamp suffix picks the most recent run automatically).
#   - Reads validated_evidence, rejected_evidence, sdg_summaries, and run-level
#     metadata from every matched folder.
#   - Unnests candidate_sdgs and evidence_tags into long form for analysis.
#
# Outputs (available after source("R/load_evidence.R")):
#   ev         — long form: one row per evidence-item × SDG
#   ev_wide    — wide form: one row per evidence item (tags as list-columns)
#   ev_rej     — rejected evidence (wide form)
#   sdg_yr     — SDG summaries: one row per SDG × year × company
#   run_meta   — one row per run (company, year, overall_assessment, counts)
# ─────────────────────────────────────────────────────────────────────────────

suppressPackageStartupMessages({
  library(tidyverse)
  library(jsonlite)
  library(fs)
})

# ── Configuration ─────────────────────────────────────────────────────────────

# Path to pipeline outputs, relative to the analysis/ working directory
OUTPUTS_DIR <- here::here("..", "data", "outputs")

# Add new companies here as more are processed
COMPANIES <- c("coromandel", "jswsteel")

# ── Helper: find latest folder for each company × year ───────────────────────

find_latest_folders <- function(outputs_dir, companies) {
  # Folders are named: {company}_{year}_{YYYYMMDD}_{HHMMSS}/
  all_folders <- fs::dir_ls(outputs_dir, type = "directory")

  map_dfr(companies, function(co) {
    pattern <- paste0("^", co, "_\\d{4}_")
    matched <- all_folders[str_detect(fs::path_file(all_folders), regex(pattern, ignore_case = TRUE))]

    if (length(matched) == 0) return(tibble())

    tibble(folder = as.character(matched)) |>
      mutate(
        folder_name = fs::path_file(folder),
        company     = co,
        year        = as.integer(str_extract(folder_name, "(?<=_)\\d{4}(?=_)")),
        timestamp   = str_extract(folder_name, "\\d{8}_\\d{6}$")
      ) |>
      filter(!is.na(year), !is.na(timestamp)) |>
      group_by(company, year) |>
      slice_max(timestamp, n = 1, with_ties = FALSE) |>   # latest run per year
      ungroup()
  })
}

# ── Helper: find latest report.md for each company × year ────────────────────

find_latest_report_mds <- function(outputs_dir = OUTPUTS_DIR,
                                    companies   = COMPANIES) {
  find_latest_folders(outputs_dir, companies) |>
    mutate(report_md = as.character(fs::path(folder, "report.md"))) |>
    filter(fs::file_exists(report_md)) |>
    arrange(company, year)
}

# ── Helper: read one evidence.json ───────────────────────────────────────────

read_evidence_json <- function(folder_path, company, year) {
  json_path <- fs::path(folder_path, "evidence.json")
  if (!fs::file_exists(json_path)) {
    warning("No evidence.json in: ", folder_path)
    return(NULL)
  }

  raw <- fromJSON(json_path, simplifyVector = FALSE)

  # ── run-level metadata ───────────────────────────────────────────────────
  meta <- tibble(
    company            = tolower(raw$company %||% company),
    report_name        = raw$report_name %||% NA_character_,
    report_year        = raw$report_year %||% year,
    overall_assessment = raw$overall_assessment %||% NA_character_,
    folder             = folder_path
  )

  # ── validated evidence ────────────────────────────────────────────────────
  ev_raw <- raw$validated_evidence
  ev_df  <- if (length(ev_raw) == 0) {
    tibble()
  } else {
    map_dfr(ev_raw, function(item) {
      tibble(
        evidence_id          = item$evidence_id        %||% NA_character_,
        company              = tolower(item$company     %||% company),
        report_name          = item$report_name        %||% NA_character_,
        report_year          = item$report_year        %||% year,
        page_number          = item$page_number        %||% NA_integer_,
        section_heading      = item$section_heading    %||% NA_character_,
        evidence_text        = item$evidence_text      %||% NA_character_,
        evidence_summary     = item$evidence_summary   %||% NA_character_,
        candidate_sdgs       = list(unlist(item$candidate_sdgs) %||% character(0)),
        evidence_tags        = list(unlist(item$evidence_tags)  %||% character(0)),
        implementation_stage = item$implementation_stage %||% NA_character_,
        quantitative_support = item$quantitative_support %||% FALSE,
        oversight_support    = item$oversight_support    %||% FALSE,
        confidence           = item$confidence           %||% NA_real_,
        rationale            = item$rationale            %||% NA_character_,
        validation_status    = item$validation_status    %||% "valid",
        computed_strength    = item$computed_strength    %||% NA_character_,
        computed_score       = item$computed_score       %||% NA_integer_
      )
    })
  }

  # ── rejected evidence ─────────────────────────────────────────────────────
  rej_raw <- raw$rejected_evidence
  rej_df  <- if (length(rej_raw) == 0) {
    tibble()
  } else {
    map_dfr(rej_raw, function(item) {
      tibble(
        evidence_id          = item$evidence_id        %||% NA_character_,
        company              = tolower(item$company     %||% company),
        report_year          = item$report_year        %||% year,
        page_number          = item$page_number        %||% NA_integer_,
        evidence_text        = item$evidence_text      %||% NA_character_,
        implementation_stage = item$implementation_stage %||% NA_character_,
        validation_errors    = list(unlist(item$validation_errors) %||% character(0)),
        computed_score       = item$computed_score %||% NA_integer_
      )
    })
  }

  # ── SDG summaries ─────────────────────────────────────────────────────────
  sdg_raw <- raw$sdg_summaries
  sdg_df  <- if (length(sdg_raw) == 0) {
    tibble()
  } else {
    map_dfr(sdg_raw, function(s) {
      tibble(
        company                = company,
        report_year            = year,
        sdg                    = s$sdg                    %||% NA_character_,
        evidence_count         = s$evidence_count         %||% 0L,
        average_score          = s$average_score          %||% NA_real_,
        implementation_profile = s$implementation_profile %||% NA_character_,
        summary                = s$summary                %||% NA_character_
      )
    })
  }

  list(meta = meta, ev = ev_df, rej = rej_df, sdg = sdg_df)
}

# ── Null-coalescing operator (base R doesn't have one) ────────────────────────
`%||%` <- function(x, y) if (!is.null(x) && length(x) > 0) x else y

# ── Main loader ───────────────────────────────────────────────────────────────

load_all_evidence <- function(outputs_dir = OUTPUTS_DIR,
                               companies   = COMPANIES) {
  folders <- find_latest_folders(outputs_dir, companies)

  if (nrow(folders) == 0) {
    stop("No output folders found in: ", outputs_dir)
  }

  message("Loading ", nrow(folders), " run(s) from ", outputs_dir, " ...")

  results <- pmap(list(folders$folder, folders$company, folders$year),
                  read_evidence_json)
  results <- compact(results)

  if (length(results) == 0) stop("No evidence.json files could be read.")

  # ── Assemble wide evidence table ─────────────────────────────────────────
  ev_wide <- map_dfr(results, "ev") |>
    mutate(
      # Ensure report_year is always a plain integer (not list-column from JSON)
      report_year = as.integer(unlist(report_year)),
      # Ordered factor for implementation stage
      implementation_stage = factor(
        implementation_stage,
        levels = c("mention_only", "planned_action",
                   "implementation_in_progress",
                   "implemented_with_measurable_evidence"),
        ordered = TRUE
      ),
      computed_strength = factor(
        computed_strength,
        levels = c("weak", "moderate", "strong"),
        ordered = TRUE
      ),
      # Period label (annual vs integrated reporting era)
      period = if_else(report_year <= 2021, "Annual (2016–2021)",
                                            "Integrated (2022–2025)")
    )

  # ── Long form: one row per evidence × SDG ────────────────────────────────
  ev <- ev_wide |>
    unnest(candidate_sdgs) |>
    rename(sdg = candidate_sdgs) |>
    mutate(
      sdg_num = as.integer(str_extract(sdg, "\\d+")),
      sdg     = fct_reorder(sdg, sdg_num)
    )

  # ── Rejected evidence ─────────────────────────────────────────────────────
  ev_rej <- map_dfr(results, "rej")

  # ── SDG summaries ─────────────────────────────────────────────────────────
  sdg_yr <- map_dfr(results, "sdg") |>
    mutate(
      sdg_num = as.integer(str_extract(sdg, "\\d+")),
      sdg     = fct_reorder(sdg, sdg_num),
      period  = if_else(report_year <= 2021, "Annual (2016–2021)",
                                             "Integrated (2022–2025)")
    )

  # ── Run metadata ──────────────────────────────────────────────────────────
  run_meta <- map_dfr(results, "meta") |>
    left_join(
      ev_wide |>
        count(company, report_year, name = "n_valid"),
      by = c("company", "report_year")
    ) |>
    left_join(
      ev_rej |>
        count(company, report_year, name = "n_rejected"),
      by = c("company", "report_year")
    ) |>
    mutate(
      n_valid    = replace_na(n_valid, 0L),
      n_rejected = replace_na(n_rejected, 0L),
      rejection_rate = n_rejected / (n_valid + n_rejected)
    )

  message("Loaded: ", nrow(ev_wide), " valid evidence items, ",
          nrow(ev_rej), " rejected, across ",
          n_distinct(ev_wide$report_year), " year(s) and ",
          n_distinct(ev_wide$company), " company/companies.")

  list(ev = ev, ev_wide = ev_wide, ev_rej = ev_rej,
       sdg_yr = sdg_yr, run_meta = run_meta)
}

# ── Convenience: load at source time and expose to global env ─────────────────
.sdg_data   <- load_all_evidence()
ev          <- .sdg_data$ev
ev_wide     <- .sdg_data$ev_wide
ev_rej      <- .sdg_data$ev_rej
sdg_yr      <- .sdg_data$sdg_yr
run_meta    <- .sdg_data$run_meta
