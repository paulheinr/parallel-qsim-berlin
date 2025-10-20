#!/usr/bin/env Rscript

library(tidyverse)

routing_threads <- 4  # adjust if needed

# --- Path to your subfolder ---
data_path <- sprintf("output/v6.4/1pct-12-router-%d/instrument", routing_threads)

# --- List and read all instrument_process_*.csv files ---
files <- list.files(data_path, pattern = "^instrument_process_\\d+\\.csv$", full.names = TRUE)

data <- files %>%
  map_dfr(function(f) {
    # extract number after underscore
    rank_num <- str_extract(basename(f), "(?<=instrument_process_)\\d+")
    read_csv(f, show_col_types = FALSE) %>%
      mutate(rank = as.integer(rank_num))
  })

# --- Inspect ---
cat("Columns in combined data:\n")
print(colnames(data))
cat("Number of rows:", nrow(data), "\n")

# --- Filter to the function of interest ---
replace_route_data <- data %>% filter(func_name == "blocking_recv")

# summarize replace_route_data
cat("Summary of blocking_recv data:\n")
print(summary(replace_route_data))

# print sum of all replace route durations
total_blocking_duration <- sum(replace_route_data$duration, na.rm = TRUE)
cat(sprintf("Total blocking_recv duration (ns): %f\n", total_blocking_duration))

# summarize call_router
cat("Summary of call_router data:\n")
print(summary(data %>% filter(func_name == "call_router")))

# --- Plot sim_time (x) vs duration (y) ---
ggplot(replace_route_data, aes(x = sim_time, y = duration, color = factor(rank))) +
  geom_point(alpha = 0.5, size = 1) +
  scale_y_log10() +
  labs(
    title = sprintf("Duration of blocking_recv over Simulation Time - %d Routing Threads", routing_threads),
    x = "Simulation Time",
    y = "Duration (ns)",
    color = "Rank"
  ) +
  theme_minimal(base_size = 24)

# --- Sum total blocking_recv duration per rank and bar chart ---
blocking_totals <- data %>%
  filter(func_name == "blocking_recv") %>%
  group_by(rank) %>%
  summarise(total_duration_ns = sum(duration, na.rm = TRUE), .groups = "drop")

# Bar chart (log scale on Y for readability if values vary a lot)
ggplot(blocking_totals, aes(x = factor(rank), y = total_duration_ns)) +
  geom_col(fill = "steelblue") +
  scale_y_log10() +
  labs(
    title = sprintf("Total blocking_recv duration per rank - %d Routing Threads", routing_threads),
    x = "Rank",
    y = "Total duration (ns, log scale)"
  ) +
  theme_minimal(base_size = 24)

# --- Sum total call_router duration per rank and bar chart ---
call_router_totals <- data %>%
  filter(func_name == "call_router") %>%
  group_by(rank) %>%
  summarise(total_duration_ns = sum(duration, na.rm = TRUE), .groups = "drop")

ggplot(call_router_totals, aes(x = factor(rank), y = total_duration_ns)) +
  geom_col(fill = "darkgreen") +
  scale_y_log10() +
  labs(
    title = sprintf("Total call_router duration per rank - %d Routing Threads", routing_threads),
    x = "Rank",
    y = "Total duration (ns, log scale)"
  ) +
  theme_minimal(base_size = 24)

