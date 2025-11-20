theme_increase_all_text <- function(increase = 1.5, base_size = 11, base_family = "") {
  theme_minimal(base_size = base_size * increase, base_family = base_family) +
    theme(
      plot.title = element_text(size = rel(1.2)),
      axis.title = element_text(size = rel(1.0)),
      axis.text = element_text(size = rel(0.95)),
      legend.title = element_text(size = rel(1.0)),
      legend.text = element_text(size = rel(0.95)),
      strip.text = element_text(size = rel(1.0)),
      # ensure default text element is also scaled
      text = element_text(size = base_size * increase)
    )
}