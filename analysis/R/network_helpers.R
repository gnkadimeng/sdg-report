# R/network_helpers.R
# ─────────────────────────────────────────────────────────────────────────────
# Network builders for the SDG interaction maps (Chapter 4).
#
# Three network types:
#   1. SDG × Evidence Tag bipartite graph
#   2. SDG × Implementation Stage bipartite graph
#   3. SDG co-occurrence graph
#
# Each returns a tidygraph object ready for ggraph or visNetwork rendering.
# ─────────────────────────────────────────────────────────────────────────────

suppressPackageStartupMessages({
  library(tidyverse)
  library(tidygraph)
  library(ggraph)
  library(igraph)
})

# ── 1. SDG × Evidence Tag bipartite network ───────────────────────────────────
#
# Nodes: SDGs (type = "sdg") + evidence tags (type = "tag")
# Edges: co-occurrence, weight = count, score_weight = avg computed_score

build_sdg_tag_network <- function(ev, filter_year = NULL, filter_period = NULL) {

  data <- ev
  if (!is.null(filter_year))   data <- filter(data, report_year %in% filter_year)
  if (!is.null(filter_period)) data <- filter(data, period %in% filter_period)

  # Unnest tags → one row per evidence × SDG × tag
  edges <- data |>
    unnest(evidence_tags) |>
    rename(tag = evidence_tags) |>
    group_by(sdg, tag) |>
    summarise(
      count       = n(),
      avg_score   = mean(computed_score, na.rm = TRUE),
      .groups = "drop"
    ) |>
    rename(from = sdg, to = tag)

  if (nrow(edges) == 0) return(NULL)

  # Node table
  sdg_nodes <- tibble(
    name      = unique(as.character(edges$from)),
    node_type = "SDG",
    colour    = SDG_COLOURS[name],
    type      = FALSE
  )
  tag_nodes <- tibble(
    name      = unique(edges$to),
    node_type = "Tag",
    colour    = "#555555",
    type      = TRUE
  )
  nodes <- bind_rows(sdg_nodes, tag_nodes)

  edges <- edges |>
    mutate(from = as.character(from))

  tbl_graph(nodes = nodes, edges = edges, directed = FALSE)
}

# ── 2. SDG × Implementation Stage bipartite network ──────────────────────────

build_sdg_stage_network <- function(ev, filter_year = NULL, filter_period = NULL) {

  data <- ev
  if (!is.null(filter_year))   data <- filter(data, report_year %in% filter_year)
  if (!is.null(filter_period)) data <- filter(data, period %in% filter_period)

  stage_labels <- c(
    "mention_only"                         = "Mention only",
    "planned_action"                       = "Planned action",
    "implementation_in_progress"           = "In progress",
    "implemented_with_measurable_evidence" = "Measurable evidence"
  )

  edges <- data |>
    mutate(stage_label = stage_labels[as.character(implementation_stage)]) |>
    group_by(sdg, stage_label) |>
    summarise(
      count     = n(),
      avg_score = mean(computed_score, na.rm = TRUE),
      .groups   = "drop"
    ) |>
    rename(from = sdg, to = stage_label)

  if (nrow(edges) == 0) return(NULL)

  sdg_nodes <- tibble(
    name      = unique(as.character(edges$from)),
    node_type = "SDG",
    colour    = SDG_COLOURS[name],
    type      = FALSE
  )
  stage_nodes <- tibble(
    name      = unique(edges$to),
    node_type = "Stage",
    colour    = c(
      "Mention only"        = "#FEE0D2",
      "Planned action"      = "#FC9272",
      "In progress"         = "#DE2D26",
      "Measurable evidence" = "#67000D"
    )[unique(edges$to)],
    type      = TRUE
  )
  nodes <- bind_rows(sdg_nodes, stage_nodes)

  edges <- edges |> mutate(from = as.character(from))

  tbl_graph(nodes = nodes, edges = edges, directed = FALSE)
}

# ── 3. SDG co-occurrence network ──────────────────────────────────────────────

build_sdg_cooccurrence_network <- function(ev_wide,
                                           filter_year   = NULL,
                                           filter_period = NULL) {
  data <- ev_wide
  if (!is.null(filter_year))   data <- filter(data, report_year %in% filter_year)
  if (!is.null(filter_period)) data <- filter(data, period %in% filter_period)

  multi <- data |> filter(map_int(candidate_sdgs, length) > 1)
  if (nrow(multi) == 0) return(NULL)

  pairs <- multi |>
    mutate(pairs = map(candidate_sdgs, function(sdgs) {
      sdgs <- sort(unique(sdgs))
      if (length(sdgs) < 2) return(tibble(from = character(), to = character()))
      combn(sdgs, 2, simplify = FALSE) |>
        map_dfr(~tibble(from = .x[1], to = .x[2]))
    })) |>
    select(pairs) |>
    unnest(pairs)

  if (nrow(pairs) == 0 || !all(c("from", "to") %in% names(pairs))) return(NULL)

  pairs <- pairs |> count(from, to, name = "count")

  if (nrow(pairs) == 0) return(NULL)

  all_sdgs <- union(pairs$from, pairs$to)
  nodes <- tibble(
    name      = all_sdgs,
    node_type = "SDG",
    colour    = SDG_COLOURS[all_sdgs],
    sdg_num   = as.integer(str_extract(all_sdgs, "\\d+"))
  )

  tbl_graph(nodes = nodes, edges = pairs, directed = FALSE)
}

# ── ggraph plot: bipartite SDG × Tag (or Stage) ───────────────────────────────

plot_bipartite_network <- function(g, title = "", count_col = "count",
                                   score_col = "avg_score") {
  if (is.null(g)) {
    return(ggplot() + labs(title = "No data for this selection") + theme_sdg())
  }

  ggraph(g, layout = "bipartite") +
    geom_edge_link(
      aes(width = .data[[count_col]],
          colour = .data[[score_col]]),
      alpha = 0.75,
      show.legend = TRUE
    ) +
    scale_edge_width(range = c(0.3, 4), name = "Evidence count") +
    scale_edge_colour_gradient(
      low = "#D9EAD3", high = "#19486A",
      name = "Avg. score"
    ) +
    geom_node_point(aes(colour = node_type, size = node_type)) +
    scale_colour_manual(
      values = c("SDG" = "#19486A", "Tag" = "#666666", "Stage" = "#CC0000"),
      name = "Node type"
    ) +
    scale_size_manual(
      values = c("SDG" = 5, "Tag" = 3, "Stage" = 3),
      guide = "none"
    ) +
    geom_node_label(
      aes(label = name),
      repel       = TRUE,
      size        = 3,
      label.size  = 0,
      fill        = alpha("white", 0.8)
    ) +
    labs(title = title) +
    theme_graph(base_family = "sans") +
    theme(legend.position = "right")
}

# ── visNetwork: interactive version of the SDG × Tag network ─────────────────

plot_interactive_network <- function(g, title = "") {
  if (is.null(g)) return(NULL)

  suppressPackageStartupMessages(library(visNetwork))

  nodes_df <- as_tibble(activate(g, nodes)) |>
    mutate(
      id    = row_number(),
      label = name,
      color = if_else(node_type == "SDG",
                      SDG_COLOURS[name] %||% "#19486A",
                      "#888888"),
      shape = if_else(node_type == "SDG", "ellipse", "box"),
      size  = if_else(node_type == "SDG", 25, 18),
      font.size = 13
    )

  edges_df <- as_tibble(activate(g, edges)) |>
    mutate(
      value = count,
      title = paste0("Count: ", count,
                     "<br>Avg score: ", round(avg_score, 2))
    )

  visNetwork(nodes_df, edges_df, main = title,
             width = "100%", height = "520px") |>
    visOptions(highlightNearest = list(enabled = TRUE, degree = 1),
               nodesIdSelection = TRUE) |>
    visPhysics(stabilization = TRUE,
               barnesHut = list(gravitationalConstant = -3000)) |>
    visLayout(randomSeed = 42)
}
