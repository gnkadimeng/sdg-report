# download_helpers.R
# Writes CSV + XLSX to downloads/ dir (served as static assets).
# Returns an htmltools button bar to place above any table.

flatten_list_cols <- function(df) {
  dplyr::mutate(df, dplyr::across(
    where(is.list),
    ~sapply(.x, function(v) paste(v, collapse = ", "))
  ))
}

make_download_bar <- function(data, basename) {
  dl_dir <- here::here("downloads")
  if (!dir.exists(dl_dir)) dir.create(dl_dir, recursive = TRUE)

  flat <- flatten_list_cols(as.data.frame(data))
  write.csv(flat,          file.path(dl_dir, paste0(basename, ".csv")),  row.names = FALSE)
  writexl::write_xlsx(flat, file.path(dl_dir, paste0(basename, ".xlsx")))

  btn <- paste0(
    "display:inline-flex;align-items:center;gap:4px;",
    "margin:0 4px 6px 0;padding:4px 12px;border-radius:6px;",
    "font-size:0.76rem;font-weight:600;text-decoration:none;",
    "border:1px solid #19486A;color:#19486A;background:#fff;",
    "transition:background 0.15s;cursor:pointer;"
  )

  htmltools::div(
    style = "text-align:right;margin-bottom:2px;",
    htmltools::a(
      href = paste0("downloads/", basename, ".csv"),
      download = NA, style = btn,
      "\u2193 CSV"
    ),
    htmltools::a(
      href = paste0("downloads/", basename, ".xlsx"),
      download = NA, style = btn,
      "\u2193 Excel"
    )
  )
}
