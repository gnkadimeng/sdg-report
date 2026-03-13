# R/plot_themes.R
# ─────────────────────────────────────────────────────────────────────────────
# Shared ggplot2 theme and official UN SDG colour palette.
# Source this file once per chapter.
# ─────────────────────────────────────────────────────────────────────────────

library(ggplot2)
library(scales)

# ── Official UN SDG colours ───────────────────────────────────────────────────

SDG_COLOURS <- c(
  "SDG 1"  = "#E5243B",   # No Poverty
  "SDG 2"  = "#DDA63A",   # Zero Hunger
  "SDG 3"  = "#4C9F38",   # Good Health
  "SDG 4"  = "#C5192D",   # Quality Education
  "SDG 5"  = "#FF3A21",   # Gender Equality
  "SDG 6"  = "#26BDE2",   # Clean Water
  "SDG 7"  = "#FCC30B",   # Affordable Energy
  "SDG 8"  = "#A21942",   # Decent Work
  "SDG 9"  = "#FD6925",   # Industry & Innovation
  "SDG 10" = "#DD1367",   # Reduced Inequalities
  "SDG 11" = "#FD9D24",   # Sustainable Cities
  "SDG 12" = "#BF8B2E",   # Responsible Consumption
  "SDG 13" = "#3F7E44",   # Climate Action
  "SDG 14" = "#0A97D9",   # Life Below Water
  "SDG 15" = "#56C02B",   # Life on Land
  "SDG 16" = "#00689D",   # Peace & Justice
  "SDG 17" = "#19486A"    # Partnerships
)

# Maturity stage colours (light → dark = weak → strong)
STAGE_COLOURS <- c(
  "mention_only"                          = "#FEE0D2",
  "planned_action"                        = "#FC9272",
  "implementation_in_progress"            = "#DE2D26",
  "implemented_with_measurable_evidence"  = "#67000D"
)

STAGE_LABELS <- c(
  "mention_only"                          = "Mention only",
  "planned_action"                        = "Planned action",
  "implementation_in_progress"            = "In progress",
  "implemented_with_measurable_evidence"  = "Measurable evidence"
)

STRENGTH_COLOURS <- c(
  "weak"     = "#D9EAD3",
  "moderate" = "#6AA84F",
  "strong"   = "#274E13"
)

# ── Shared theme ──────────────────────────────────────────────────────────────

theme_sdg <- function(base_size = 12, base_family = "sans") {
  theme_minimal(base_size = base_size, base_family = base_family) +
    theme(
      plot.title       = element_text(face = "bold", size = base_size + 2,
                                      colour = "#19486A"),
      plot.subtitle    = element_text(colour = "grey40", size = base_size - 1,
                                      margin = margin(b = 8)),
      plot.caption     = element_text(colour = "grey55", size = base_size - 3,
                                      hjust = 0),
      axis.title       = element_text(colour = "grey30", size = base_size - 1),
      axis.text        = element_text(colour = "grey40"),
      panel.grid.major = element_line(colour = "grey92"),
      panel.grid.minor = element_blank(),
      legend.position  = "bottom",
      legend.title     = element_text(face = "bold", size = base_size - 1),
      strip.text       = element_text(face = "bold", colour = "#19486A"),
      plot.margin      = margin(12, 12, 8, 12)
    )
}

# Set as default
theme_set(theme_sdg())

# ── Helper: SDG fill scale ─────────────────────────────────────────────────────

scale_fill_sdg <- function(...) {
  scale_fill_manual(values = SDG_COLOURS, ...)
}

scale_colour_sdg <- function(...) {
  scale_colour_manual(values = SDG_COLOURS, ...)
}

scale_fill_stage <- function(...) {
  scale_fill_manual(values = STAGE_COLOURS, labels = STAGE_LABELS, ...)
}

scale_colour_stage <- function(...) {
  scale_colour_manual(values = STAGE_COLOURS, labels = STAGE_LABELS, ...)
}

scale_fill_strength <- function(...) {
  scale_fill_manual(values = STRENGTH_COLOURS, ...)
}

scale_colour_strength <- function(...) {
  scale_colour_manual(values = STRENGTH_COLOURS, ...)
}

# ── Helper: SDG number label (for axis) ───────────────────────────────────────

sdg_short_label <- function(sdg_vec) {
  # "SDG 13" → "SDG\n13"
  str_replace(sdg_vec, "SDG (\\d+)", "SDG\n\\1")
}
