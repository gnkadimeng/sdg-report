# ============================================================
# SINGLE SCRIPT:
# Realistic simulation of firm-year SDG panel data, mixed models,
# annotations, and multi-panel figures with patchwork
# ============================================================

# -----------------------------
# 0. Packages
# -----------------------------
required_pkgs <- c(
  "dplyr", "tidyr", "ggplot2", "lme4", "lmerTest", "patchwork"
)

to_install <- required_pkgs[!sapply(required_pkgs, requireNamespace, quietly = TRUE)]
if (length(to_install) > 0) {
  stop(
    "Please install missing packages first: ",
    paste(to_install, collapse = ", ")
  )
}

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(ggplot2)
  library(lme4)
  library(lmerTest)
  library(patchwork)
})

set.seed(1234)

# ============================================================
# 1. Study design
# ============================================================

years <- 2020:2023
countries <- c("India", "South Africa")

sectors <- c(
  "Basic Materials",
  "Communication Services",
  "Consumer Cyclical",
  "Consumer Defensive",
  "Energy",
  "Financial Services",
  "Healthcare",
  "Industrials",
  "Real Estate",
  "Technology",
  "Utilities"
)

n_sdgs  <- 17
n_firms <- 220

sector_probs <- c(0.08, 0.07, 0.10, 0.08, 0.08, 0.12, 0.10, 0.12, 0.07, 0.12, 0.06)
stopifnot(length(sector_probs) == length(sectors))
stopifnot(abs(sum(sector_probs) - 1) < 1e-8)

# ============================================================
# 2. Helper functions
# ============================================================

make_template <- function(n_sdgs, favoured = integer(0), boost = 2.5, base = 1) {
  x <- rep(base, n_sdgs)
  if (length(favoured) > 0) {
    x[favoured] <- x[favoured] * boost
  }
  x
}

compute_vif <- function(mat) {
  vif_vals <- sapply(seq_len(ncol(mat)), function(i) {
    y <- mat[, i]
    x <- mat[, -i, drop = FALSE]
    mod <- lm(y ~ x)
    1 / (1 - summary(mod)$r.squared)
  })
  
  data.frame(
    term = colnames(mat),
    VIF = as.numeric(vif_vals),
    row.names = NULL
  )
}

predict_fixed_ci <- function(model, newdata) {
  tt <- delete.response(terms(model))
  X <- model.matrix(tt, newdata)
  beta <- lme4::fixef(model)
  V <- as.matrix(vcov(model))
  
  fit <- as.numeric(X %*% beta)
  se  <- sqrt(diag(X %*% V %*% t(X)))
  
  out <- newdata
  out$fit <- fit
  out$se  <- se
  out$lwr <- fit - 1.96 * se
  out$upr <- fit + 1.96 * se
  out
}

extract_profile_metrics <- function(df) {
  if (!all(c("sdg", "score") %in% names(df))) {
    stop("Profile data frame must contain 'sdg' and 'score' columns.")
  }
  
  if (nrow(df) < 2) {
    stop("Profile must contain at least 2 SDGs.")
  }
  
  s <- df$score / 100
  
  if (abs(sum(s) - 1) > 1e-8) {
    stop("Scores do not sum to 100.")
  }
  
  ord <- order(df$score, decreasing = TRUE)
  
  top1 <- df$score[ord[1]]
  top2 <- sum(df$score[ord[1:2]])
  hhi  <- sum(s^2)
  entropy <- -sum(s * log(s))
  dom_sdg <- df$sdg[ord[1]]
  
  tibble(
    dominant_score = top1,
    top2_score     = top2,
    hhi            = hhi,
    entropy        = entropy,
    dominant_sdg   = dom_sdg
  )
}

country_sector_adj <- function(country, sector) {
  out <- 0
  
  if (country == "India" && sector == "Technology") {
    out <- out + 1.0
  }
  if (country == "South Africa" && sector == "Utilities") {
    out <- out + 0.8
  }
  if (country == "South Africa" && sector == "Real Estate") {
    out <- out - 0.8
  }
  
  out
}

country_year_adj <- function(country, year) {
  out <- 0
  
  if (country == "India" && year == 2023) {
    out <- out + 0.6
  }
  if (country == "South Africa" && year == 2021) {
    out <- out - 0.5
  }
  if (country == "South Africa" && year == 2022) {
    out <- out - 0.4
  }
  
  out
}

# ============================================================
# 3. Sector, country, and year SDG templates
# ============================================================

sector_sdg_templates <- list(
  "Basic Materials"        = make_template(n_sdgs, favoured = c(9, 12, 13)),
  "Communication Services" = make_template(n_sdgs, favoured = c(9, 10, 16)),
  "Consumer Cyclical"      = make_template(n_sdgs, favoured = c(8, 9, 12)),
  "Consumer Defensive"     = make_template(n_sdgs, favoured = c(2, 3, 12)),
  "Energy"                 = make_template(n_sdgs, favoured = c(7, 9, 13)),
  "Financial Services"     = make_template(n_sdgs, favoured = c(8, 9, 10, 16)),
  "Healthcare"             = make_template(n_sdgs, favoured = c(3, 5, 10)),
  "Industrials"            = make_template(n_sdgs, favoured = c(8, 9, 11, 12)),
  "Real Estate"            = make_template(n_sdgs, favoured = c(9, 11, 12, 13)),
  "Technology"             = make_template(n_sdgs, favoured = c(4, 8, 9, 10)),
  "Utilities"              = make_template(n_sdgs, favoured = c(6, 7, 9, 11, 13))
)

country_sdg_templates <- list(
  "India"        = make_template(n_sdgs, favoured = c(8, 9, 10), boost = 1.4),
  "South Africa" = make_template(n_sdgs, favoured = c(6, 7, 10, 11), boost = 1.4)
)

year_sdg_templates <- list(
  "2020" = make_template(n_sdgs, favoured = c(3, 8, 12), boost = 1.10),
  "2021" = make_template(n_sdgs, favoured = c(3, 8, 13), boost = 1.15),
  "2022" = make_template(n_sdgs, favoured = c(7, 9, 12, 13), boost = 1.12),
  "2023" = make_template(n_sdgs, favoured = c(9, 12, 13), boost = 1.18)
)

simulate_firm_baseline <- function(country, sector, n_sdgs = 17) {
  sector_base  <- sector_sdg_templates[[sector]]
  country_base <- country_sdg_templates[[country]]
  
  idiosyncratic <- rgamma(n_sdgs, shape = 1.5, rate = 1)
  
  raw <- sector_base * country_base * idiosyncratic
  raw / sum(raw)
}

simulate_sdg_profile_realistic <- function(firm_row, concentration_signal, n_sdgs = 17) {
  if (!is.finite(concentration_signal)) {
    stop("concentration_signal must be finite.")
  }
  
  base_profile <- as.numeric(firm_row[paste0("SDG", seq_len(n_sdgs))])
  year_profile <- year_sdg_templates[[as.character(firm_row[["year"]])]]
  
  country_tilt <- if (firm_row[["country"]] == "India") {
    make_template(n_sdgs, favoured = c(8, 9), boost = 1.05)
  } else {
    make_template(n_sdgs, favoured = c(6, 10, 11), boost = 1.05)
  }
  
  alpha_base <- base_profile * year_profile * country_tilt
  
  signal_clamped <- max(min(concentration_signal, 25), -25)
  concentration_multiplier <- exp(signal_clamped / 10)
  
  total_mass <- 20 / concentration_multiplier
  total_mass <- pmin(pmax(total_mass, 2.5), 40)
  
  alpha <- alpha_base * total_mass
  
  draw <- rgamma(n_sdgs, shape = alpha, rate = 1)
  probs <- draw / sum(draw)
  
  tibble(
    sdg = paste0("SDG", seq_len(n_sdgs)),
    score = 100 * probs
  )
}

# ============================================================
# 4. Firm-level data
# ============================================================

firm_df <- tibble(
  firm_id = sprintf("F%03d", 1:n_firms),
  country = sample(countries, n_firms, replace = TRUE, prob = c(0.55, 0.45)),
  sector  = sample(sectors, n_firms, replace = TRUE, prob = sector_probs),
  firm_size = round(rlnorm(n_firms, meanlog = 8.5, sdlog = 0.8)),
  reporting_framework = rbinom(n_firms, 1, 0.55)
) %>%
  mutate(
    regulatory_intensity = if_else(
      country == "India",
      rnorm(n(), mean = 0.60, sd = 0.12),
      rnorm(n(), mean = 0.50, sd = 0.12)
    ),
    regulatory_intensity = pmin(pmax(regulatory_intensity, 0.10), 1.00),
    u_firm = rnorm(n(), mean = 0, sd = 7.5)
  )

log_size_raw <- log(firm_df$firm_size)
log_size_center <- mean(log_size_raw)
log_size_scale  <- sd(log_size_raw)

if (log_size_scale == 0) {
  stop("log(firm_size) has zero variance; cannot scale.")
}

firm_df <- firm_df %>%
  mutate(
    log_size_z = (log(firm_size) - log_size_center) / log_size_scale
  )

firm_profiles <- lapply(seq_len(nrow(firm_df)), function(i) {
  simulate_firm_baseline(
    country = firm_df$country[i],
    sector  = firm_df$sector[i],
    n_sdgs  = n_sdgs
  )
})

firm_profile_mat <- do.call(rbind, firm_profiles)
colnames(firm_profile_mat) <- paste0("SDG", seq_len(n_sdgs))

firm_df <- bind_cols(
  firm_df,
  as_tibble(firm_profile_mat, .name_repair = "minimal")
)

# ============================================================
# 5. Expand to panel and make it unbalanced
# ============================================================

panel <- firm_df %>%
  tidyr::expand_grid(year = years) %>%
  arrange(firm_id, year)

expected_full_n <- n_firms * length(years)
stopifnot(nrow(panel) == expected_full_n)

set.seed(5678)

panel <- panel %>%
  mutate(
    report_prob = case_when(
      year == 2020 ~ 0.88,
      year == 2021 ~ 0.91,
      year == 2022 ~ 0.93,
      year == 2023 ~ 0.95
    ),
    keep_row = rbinom(n(), size = 1, prob = report_prob)
  ) %>%
  filter(keep_row == 1) %>%
  select(-report_prob, -keep_row)

firm_counts <- panel %>% count(firm_id)
too_sparse <- firm_counts %>% filter(n < 2) %>% pull(firm_id)

if (length(too_sparse) > 0) {
  rows_to_add <- firm_df %>%
    filter(firm_id %in% too_sparse) %>%
    slice(rep(seq_len(n()), each = 2)) %>%
    mutate(year = rep(c(2022, 2023), length.out = n()))
  
  panel <- bind_rows(panel, rows_to_add) %>%
    distinct(firm_id, year, .keep_all = TRUE) %>%
    arrange(firm_id, year)
}

stopifnot(all((panel %>% count(firm_id))$n >= 2))

# ============================================================
# 6. Latent concentration process
# ============================================================

sector_effects <- c(
  "Basic Materials"         =  0.0,
  "Communication Services"  = -0.8,
  "Consumer Cyclical"       = -1.0,
  "Consumer Defensive"      =  1.4,
  "Energy"                  = -0.2,
  "Financial Services"      = -0.9,
  "Healthcare"              =  1.1,
  "Industrials"             =  0.4,
  "Real Estate"             = -1.2,
  "Technology"              =  1.8,
  "Utilities"               =  1.5
)

year_effects <- c(
  "2020" =  0.0,
  "2021" = -0.7,
  "2022" = -0.5,
  "2023" =  0.3
)

stopifnot(all(sectors %in% names(sector_effects)))
stopifnot(all(as.character(years) %in% names(year_effects)))

panel <- panel %>%
  mutate(
    sector_main = unname(sector_effects[sector]),
    year_main   = unname(year_effects[as.character(year)]),
    cs_adj      = mapply(country_sector_adj, country, sector),
    cy_adj      = mapply(country_year_adj, country, year),
    eta = 10 +
      if_else(country == "South Africa", -1.2, 0) +
      sector_main +
      year_main +
      cs_adj +
      cy_adj +
      0.9 * reporting_framework +
      1.4 * log_size_z +
      2.2 * regulatory_intensity +
      u_firm +
      rnorm(n(), mean = 0, sd = 2.5)
  )

stopifnot(!any(is.na(panel$eta)))
stopifnot(length(panel$eta) == nrow(panel))

# ============================================================
# 7. Simulate SDG profiles for each firm-year
# ============================================================

profiles <- lapply(seq_len(nrow(panel)), function(i) {
  simulate_sdg_profile_realistic(
    firm_row = panel[i, ],
    concentration_signal = panel$eta[i],
    n_sdgs = n_sdgs
  )
})

stopifnot(length(profiles) == nrow(panel))

metric_df <- bind_rows(lapply(profiles, extract_profile_metrics))
stopifnot(nrow(metric_df) == nrow(panel))

dat <- bind_cols(panel, metric_df)

# ============================================================
# 8. Prepare variables
# ============================================================

dat <- dat %>%
  mutate(
    country = factor(country, levels = c("India", "South Africa")),
    sector  = factor(sector, levels = sectors),
    year    = factor(year, levels = as.character(years)),
    reporting_framework = factor(
      reporting_framework,
      levels = c(0, 1),
      labels = c("No", "Yes")
    ),
    dominant_sdg = factor(dominant_sdg)
  )

stopifnot(all(levels(dat$country) == c("India", "South Africa")))
stopifnot(levels(dat$sector)[1] == "Basic Materials")
stopifnot(levels(dat$year)[1] == "2020")

# ============================================================
# 9. Console summaries
# ============================================================

cat("\n====================\n")
cat("SIMULATION DASHBOARD\n")
cat("====================\n")
cat("Rows:", nrow(dat), "\n")
cat("Unique firms:", dplyr::n_distinct(dat$firm_id), "\n")
cat("Average years per firm:", round(mean((dat %>% count(firm_id))$n), 2), "\n")
cat("Mean dominant score:", round(mean(dat$dominant_score), 2), "\n")
cat("Mean HHI:", round(mean(dat$hhi), 3), "\n")
cat("Correlation (dominant score, HHI):", round(cor(dat$dominant_score, dat$hhi), 3), "\n")

cat("\n====================\n")
cat("Summary of dominant score\n")
cat("====================\n")
print(summary(dat$dominant_score))

cat("\nQuantiles of dominant score\n")
print(quantile(dat$dominant_score, probs = c(.01, .10, .25, .50, .75, .90, .99)))

cat("\n====================\n")
cat("Summary of HHI\n")
cat("====================\n")
print(summary(dat$hhi))

# ============================================================
# 10. Fit mixed-effects models
# ============================================================

ctrl <- lmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 1e5))

m1 <- lmer(
  dominant_score ~ country + sector + year + (1 | firm_id),
  data = dat,
  REML = FALSE,
  control = ctrl
)

m2 <- lmer(
  dominant_score ~ country * sector + country * year + (1 | firm_id),
  data = dat,
  REML = FALSE,
  control = ctrl
)

m3 <- lmer(
  dominant_score ~ country * sector + country * year +
    log_size_z + regulatory_intensity + reporting_framework +
    (1 | firm_id),
  data = dat,
  REML = FALSE,
  control = ctrl
)

m4 <- lmer(
  hhi ~ country * sector + country * year +
    log_size_z + regulatory_intensity + reporting_framework +
    (1 | firm_id),
  data = dat,
  REML = FALSE,
  control = ctrl
)

cat("\n====================\n")
cat("MODEL A: Main effects only\n")
cat("====================\n")
print(summary(m1))

cat("\n====================\n")
cat("MODEL B: Add country x sector and country x year\n")
cat("====================\n")
print(summary(m2))

cat("\n====================\n")
cat("MODEL C: Add controls\n")
cat("====================\n")
print(summary(m3))

cat("\n====================\n")
cat("MODEL D: HHI as alternative dependent variable\n")
cat("====================\n")
print(summary(m4))

cat("\n====================\n")
cat("Model comparison (dominant score models)\n")
cat("====================\n")
model_comp <- anova(m1, m2, m3)
print(model_comp)

cat("\nModel comparison interpretation:\n")
cat("- m1: main effects only\n")
cat("- m2: adds country x sector and country x year interactions\n")
cat("- m3: adds control variables\n")
cat("Use this to judge whether added complexity improves fit enough to justify interpretation.\n")

# ============================================================
# 11. Diagnostics
# ============================================================

cat("\n====================\n")
cat("Diagnostics for Model C\n")
cat("====================\n")

cat("\nConvergence info:\n")
print(m3@optinfo$conv$lme4$messages)

cat("\nIs model singular?\n")
print(lme4::isSingular(m3, tol = 1e-5))

diag_df <- tibble(
  fitted   = fitted(m3),
  resid    = resid(m3),
  observed = dat$dominant_score
)

cat("\nResidual summary:\n")
print(summary(diag_df$resid))

cat("\nRandom effects:\n")
print(VarCorr(m3), comp = c("Variance", "Std.Dev."))

X <- model.matrix(
  ~ country * sector + country * year +
    log_size_z + regulatory_intensity + reporting_framework,
  data = dat
)

X_noint <- X[, colnames(X) != "(Intercept)", drop = FALSE]
vif_table <- compute_vif(X_noint)

cat("\nTop 15 VIF values:\n")
print(vif_table[order(vif_table$VIF, decreasing = TRUE), ][1:min(15, nrow(vif_table)), ])

# ============================================================
# 12. Prediction data with fixed-effect confidence intervals
# ============================================================

newdat <- expand.grid(
  country = levels(dat$country),
  sector  = c("Basic Materials", "Technology", "Utilities", "Real Estate"),
  year    = levels(dat$year),
  log_size_z = 0,
  regulatory_intensity = mean(dat$regulatory_intensity),
  reporting_framework = "Yes",
  KEEP.OUT.ATTRS = FALSE,
  stringsAsFactors = FALSE
)

newdat <- newdat %>%
  mutate(
    country = factor(country, levels = levels(dat$country)),
    sector  = factor(sector, levels = levels(dat$sector)),
    year    = factor(year, levels = levels(dat$year)),
    reporting_framework = factor(
      reporting_framework,
      levels = levels(dat$reporting_framework)
    )
  )

newdat_dom <- predict_fixed_ci(m3, newdat)
newdat_hhi <- predict_fixed_ci(m4, newdat)

# ============================================================
# 13. Example profiles illustrating reviewer concern
# ============================================================

example_a <- c(45, 40, rep((100 - 85) / 15, 15))
example_b <- c(95, rep((100 - 95) / 16, 16))

example_profiles <- tibble(
  scenario = rep(c("A: 45/40 split", "B: 95 alone"), each = n_sdgs),
  sdg = rep(paste0("SDG", seq_len(n_sdgs)), 2),
  score = c(example_a, example_b)
)

example_summary <- example_profiles %>%
  group_by(scenario) %>%
  summarise(
    dominant_score = max(score),
    hhi = sum((score / 100)^2),
    entropy = -sum((score / 100) * log(score / 100)),
    .groups = "drop"
  )

cat("\n====================\n")
cat("Example contrasting profiles\n")
cat("====================\n")
print(example_summary)

cat("\nInterpretation:\n")
cat("Scenario A spreads attention across at least two major SDGs.\n")
cat("Scenario B is overwhelmingly concentrated in one SDG.\n")
cat("A top-score-only outcome misses this distinction.\n")

# ============================================================
# 14. Additional summary data for plots
# ============================================================

dominant_by_sector <- dat %>%
  count(sector, dominant_sdg) %>%
  group_by(sector) %>%
  mutate(prop = n / sum(n)) %>%
  ungroup()

cat("\n====================\n")
cat("Dominant SDG distribution by sector (top rows)\n")
cat("====================\n")
print(head(dominant_by_sector, 30))

sector_summary <- dat %>%
  group_by(sector, country) %>%
  summarise(
    mean_dom = mean(dominant_score),
    mean_hhi = mean(hhi),
    .groups = "drop"
  )

set.seed(99)
sample_firms <- sample(unique(dat$firm_id), 6)

traj_dat <- dat %>%
  filter(firm_id %in% sample_firms)

# ============================================================
# 15. Common theme
# ============================================================

common_theme <- theme_minimal(base_size = 11)

# ============================================================
# 16. Distribution plots with annotations
# ============================================================

dom_mean <- mean(dat$dominant_score)
dom_med  <- median(dat$dominant_score)

dom_hist_info <- ggplot_build(
  ggplot(dat, aes(x = dominant_score)) + geom_histogram(bins = 35)
)$data[[1]]
dom_hist_max <- max(dom_hist_info$count)

p1 <- ggplot(dat, aes(x = dominant_score)) +
  geom_histogram(bins = 35, color = "white") +
  geom_vline(xintercept = dom_mean, linetype = 2) +
  geom_vline(xintercept = dom_med, linetype = 3) +
  annotate(
    "text",
    x = dom_mean,
    y = dom_hist_max * 0.98,
    label = paste0("Mean = ", round(dom_mean, 1)),
    hjust = -0.05,
    vjust = 1
  ) +
  annotate(
    "text",
    x = dom_med,
    y = dom_hist_max * 0.85,
    label = paste0("Median = ", round(dom_med, 1)),
    hjust = -0.05,
    vjust = 1
  ) +
  annotate(
    "text",
    x = quantile(dat$dominant_score, 0.82),
    y = dom_hist_max * 0.68,
    label = "",
    hjust = 0
  ) +
  labs(
    title = "Distribution of dominant SDG score",
    subtitle = "Outcome based only on the top-scoring SDG",
    x = "Dominant SDG score (0-100)",
    y = "Count"
  ) +
  common_theme

hhi_mean <- mean(dat$hhi)

hhi_hist_info <- ggplot_build(
  ggplot(dat, aes(x = hhi)) + geom_histogram(bins = 35)
)$data[[1]]
hhi_hist_max <- max(hhi_hist_info$count)

p2 <- ggplot(dat, aes(x = hhi)) +
  geom_histogram(bins = 35, color = "white") +
  geom_vline(xintercept = hhi_mean, linetype = 2) +
  annotate(
    "text",
    x = hhi_mean,
    y = hhi_hist_max * 0.98,
    label = paste0("Mean HHI = ", round(hhi_mean, 3)),
    hjust = -0.05,
    vjust = 1
  ) +
  annotate(
    "text",
    x = quantile(dat$hhi, 0.78),
    y = hhi_hist_max * 0.70,
    label = "",
    hjust = 0
  ) +
  labs(
    title = "Distribution of HHI concentration index",
    subtitle = "Alternative outcome using the full 17-SDG profile",
    x = "HHI",
    y = "Count"
  ) +
  common_theme

p_rel <- ggplot(dat, aes(x = dominant_score, y = hhi)) +
  geom_point(alpha = 0.35) +
  geom_smooth(method = "lm", se = TRUE) +
  annotate(
    "text",
    x = quantile(dat$dominant_score, 0.12),
    y = quantile(dat$hhi, 0.92),
    label = "Related, but not identical:\nHHI reflects the full score distribution",
    hjust = 0
  ) +
  labs(
    title = "Relationship between dominant SDG score and HHI",
    subtitle = "Concentration and top-score strength are related but conceptually distinct",
    x = "Dominant SDG score",
    y = "HHI"
  ) +
  common_theme

# ============================================================
# 17. Model diagnostics plots
# ============================================================

p3 <- ggplot(diag_df, aes(x = fitted, y = resid)) +
  geom_point(alpha = 0.4) +
  geom_hline(yintercept = 0, linetype = 2) +
  labs(
    title = "Residuals vs fitted values",
    x = "Fitted values",
    y = "Residuals"
  ) +
  common_theme

p4 <- ggplot(diag_df, aes(sample = resid)) +
  stat_qq() +
  stat_qq_line() +
  labs(
    title = "QQ plot of residuals"
  ) +
  common_theme

p5_diag <- ggplot(diag_df, aes(x = fitted, y = observed)) +
  geom_point(alpha = 0.4) +
  geom_abline(slope = 1, intercept = 0, linetype = 2) +
  labs(
    title = "Observed vs fitted values",
    x = "Fitted values",
    y = "Observed values"
  ) +
  common_theme

# ============================================================
# 18. Example profiles and substantive interpretation plots
# ============================================================

p6 <- ggplot(example_profiles, aes(x = sdg, y = score)) +
  geom_col() +
  facet_wrap(~scenario, ncol = 1) +
  annotate(
    "text",
    x = 12,
    y = 42,
    label = "More distributed profile",
    data = data.frame(scenario = "A: 45/40 split"),
    hjust = 0
  ) +
  annotate(
    "text",
    x = 12,
    y = 92,
    label = "Highly concentrated profile",
    data = data.frame(scenario = "B: 95 alone"),
    hjust = 0
  ) +
  labs(
    title = "Why the dominant SDG score alone can be misleading",
    subtitle = "Two firms can differ sharply in concentration structure",
    x = NULL,
    y = "Score"
  ) +
  common_theme +
  theme(axis.text.x = element_text(angle = 90, vjust = 0.5))

p7 <- ggplot(newdat_dom, aes(x = year, y = fit, group = country, linetype = country)) +
  geom_ribbon(aes(ymin = lwr, ymax = upr, fill = country), alpha = 0.15, linetype = 0) +
  geom_line() +
  geom_point() +
  facet_wrap(~sector) +
  labs(
    title = "Predicted dominant SDG score by country, year, and sector",
    subtitle = "Fixed-effect predictions with 95% confidence intervals",
    x = "Year",
    y = "Predicted dominant SDG score"
  ) +
  common_theme

p8 <- ggplot(newdat_hhi, aes(x = year, y = fit, group = country, linetype = country)) +
  geom_ribbon(aes(ymin = lwr, ymax = upr, fill = country), alpha = 0.15, linetype = 0) +
  geom_line() +
  geom_point() +
  facet_wrap(~sector) +
  labs(
    title = "Predicted HHI by country, year, and sector",
    subtitle = "Fixed-effect predictions with 95% confidence intervals",
    x = "Year",
    y = "Predicted HHI"
  ) +
  common_theme

# ============================================================
# 19. Heatmap, sector summary, and trajectories
# ============================================================

p_heat <- ggplot(dominant_by_sector, aes(x = dominant_sdg, y = sector, fill = prop)) +
  geom_tile() +
  geom_text(aes(label = sprintf("%.2f", prop)), size = 2.5) +
  labs(
    title = "Dominant SDG composition by sector",
    subtitle = "Sector-specific dominance patterns in the simulated data",
    x = "Dominant SDG",
    y = "Sector",
    fill = "Proportion"
  ) +
  common_theme

p_sector <- ggplot(sector_summary, aes(x = mean_dom, y = mean_hhi, shape = country)) +
  geom_point(size = 3) +
  geom_text(aes(label = sector), nudge_y = 0.002, size = 3, check_overlap = TRUE) +
  labs(
    title = "Sector-level average dominant score and concentration",
    subtitle = "Labels identify sectors with stronger average concentration",
    x = "Mean dominant score",
    y = "Mean HHI"
  ) +
  common_theme

p_traj <- ggplot(traj_dat, aes(x = year, y = dominant_score, group = firm_id)) +
  geom_line() +
  geom_point() +
  facet_wrap(~firm_id) +
  labs(
    title = "Example firm-level dominant SDG score trajectories",
    subtitle = "Illustrates longitudinal structure and between-firm heterogeneity",
    x = "Year",
    y = "Dominant SDG score"
  ) +
  common_theme

# ============================================================
# 20. Patchwork panels
# ============================================================

dist_panel <- (p1 | p2) / p_rel +
  plot_annotation(
    title = "Distribution and concentration diagnostics",
    subtitle = "Comparing the top-score outcome with a full-distribution concentration measure",
    caption = "Top row: marginal distributions. Bottom row: relationship between dominant score and HHI.",
    tag_levels = "A"
  )

diag_panel <- (p3 | p4 | p5_diag) +
  plot_annotation(
    title = "Model diagnostics for the dominant-score mixed model",
    subtitle = "Residual shape, normality, and fitted-value performance",
    tag_levels = "A"
  )

reviewer_panel <- p6 / (p7 | p8) +
  plot_layout(heights = c(1, 1.2), guides = "collect") &
  theme(legend.position = "bottom")

reviewer_panel <- reviewer_panel +
  plot_annotation(
    title = "Illustrating the reviewer’s concern",
    subtitle = "Top-score simplification and interaction-sensitive predictions",
    tag_levels = "A"
  )

structure_panel <- p_heat / (p_sector | p_traj) +
  plot_layout(heights = c(1.1, 1), guides = "collect") &
  theme(legend.position = "bottom")

structure_panel <- structure_panel +
  plot_annotation(
    title = "Sectoral and longitudinal structure in the simulated data",
    subtitle = "Heatmap shows sector-specific dominance patterns; lower panels show sector summaries and example trajectories",
    tag_levels = "A"
  )

# ============================================================
# 21. Print plots and panels
# ============================================================

print(p1)
print(p2)
print(p_rel)

print(p3)
print(p4)
print(p5_diag)

print(p6)
print(p7)
print(p8)

print(p_heat)
print(p_sector)
print(p_traj)

print(dist_panel)
print(diag_panel)
print(reviewer_panel)
print(structure_panel)

# ============================================================
# 22. Optional file saving
# ============================================================
# Uncomment if needed:
# ggsave("dist_panel.png", dist_panel, width = 12, height = 8, dpi = 300)
# ggsave("diag_panel.png", diag_panel, width = 14, height = 5, dpi = 300)
# ggsave("reviewer_panel.png", reviewer_panel, width = 14, height = 10, dpi = 300)
# ggsave("structure_panel.png", structure_panel, width = 14, height = 10, dpi = 300)

# ============================================================
# 23. Final interpretation text
# ============================================================

cat("\n===========================================================\n")
cat("HOW TO READ THIS SIMULATION\n")
cat("===========================================================\n")
cat("
1. The panel is unbalanced: not every firm appears in every year.

2. Each firm has a persistent SDG orientation profile, so firms are
   not re-generated from scratch each year.

3. Sector, country, and year all shape the SDG composition.

4. The dominant-score models show what happens when only the top SDG
   score is used as the dependent variable.

5. The HHI model uses the full 17-SDG distribution and therefore
   better captures concentration versus dispersion of SDG emphasis.

6. Country x sector and country x year interactions make it possible
   to test whether sectoral patterns and time trends differ between
   India and South Africa.

7. The annotated plots are designed to show, visually, why the
   reviewer's concerns about bounded outcomes, information loss,
   and interaction structure are methodologically relevant.

8. In any simulated dataset, some interactions may be important and
   others may not be. The purpose here is illustrative.
")