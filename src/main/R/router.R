#!/usr/bin/env Rscript

# --- Libraries ---
# Install if not present: install.packages("tidyverse")
library(tidyverse)

# --- Load CSV ---
# Replace 'data.csv' with your actual file path
data <- read.csv("output/analysis/routing-profiling-4-2025-10-07_11-35-57.csv")

# --- Inspect ---
cat("Columns in file:\n")
print(colnames(data))
cat("\nFirst few rows:\n")
print(head(data))

# --- Basic statistics per thread ---
summary_stats <- data %>%
  group_by(thread) %>%
  summarise(
    count = n(),
    mean_ns = mean(duration_ns, na.rm = TRUE),
    median_ns = median(duration_ns, na.rm = TRUE),
    sd_ns = sd(duration_ns, na.rm = TRUE),
    min_ns = min(duration_ns, na.rm = TRUE),
    max_ns = max(duration_ns, na.rm = TRUE)
  ) %>%
  arrange(desc(mean_ns))

cat("\nSummary stats per thread:\n")
print(summary_stats)


# --- Plot ---
# A boxplot helps visualize distribution per thread
ggplot(data, aes(x = factor(thread), y = duration_ns / 1000000)) +
  geom_violin(trim = FALSE, fill = "lightblue", color = "black") +
  scale_y_log10(labels = scales::comma) +
  labs(
    title = "Duration (ms) per Thread",
    x = "Thread",
    y = "Duration (ms)"
  ) +
  theme_minimal()


# --- Plot total number of requests per thread ---
ggplot(summary_stats, aes(x = factor(thread), y = count)) +
  geom_col(fill = "steelblue") +
  labs(
    title = "Total Number of Requests per Thread",
    x = "Thread",
    y = "Number of Requests"
  ) +
  theme_minimal()

# --- Plot total duration per thread ---
total_duration <- data %>%
  group_by(thread) %>%
  summarise(total_duration_ns = sum(duration_ns, na.rm = TRUE), .groups = "drop")

ggplot(total_duration, aes(x = factor(thread), y = total_duration_ns)) +
  geom_col(fill = "darkorange") +
  scale_y_log10(labels = scales::comma) +
  labs(
    title = "Total Duration per Thread",
    x = "Thread",
    y = "Total Duration (ns, log scale)"
  ) +
  theme_minimal()
