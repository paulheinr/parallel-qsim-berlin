# Load necessary library
library(ggplot2)

# Read the CSV file (adjust file path as needed)
data <- read.csv("output/routing-profile.txt")

experienced_plans <- read.csv("output/times.txt")


# Convert duration from nanoseconds to seconds if needed
data$duration_ms <- data$duration_ns / 1e6

# Create the scatter plot
p <- ggplot(data, aes(x = travel_time_s / 60, y = duration_ms)) +
  geom_point() +
  scale_x_log10() +
  scale_y_log10(
    breaks = 2^(0:15),
    labels = scales::label_number()
  ) +
  labs(
    title = "Travel Time vs Duration (1000 random requests in Berlin, departure at 10am)",
    x = "Travel Time (min)",
    y = "Routing Duration (ms)"
  ) +
  theme_minimal() +
  theme(
    axis.title = element_text(size = 21),
    axis.text = element_text(size = 18),
    plot.title = element_text(size = 24)
  )
print(p)
ggsave("scatter-plot.png", plot = p, width = 15, height = 8, dpi = 400)

# Plot a histogram of routing duration
p <- ggplot(data, aes(x = duration_ms)) +
  geom_histogram(bins = 50) +
  scale_x_log10(
    breaks = 2^(0:15),
    labels = scales::label_number()
  ) +
  labs(
    title = "Histogram of Routing Duration (1000 random requests in Berlin, departure at 10am)",
    x = "Routing Duration (ms, log scale)",
    y = "Count"
  ) +
  theme_minimal() +
  theme(
    axis.title = element_text(size = 21),
    axis.text = element_text(size = 18),
    plot.title = element_text(size = 24)
  )
print(p)
ggsave("histogram.png", plot = p, width = 15, height = 8, dpi = 400)

# print statistics of routing duration
summary(data$duration_ms)

p <- ggplot(data, aes(x = "", y = duration_ms)) +
  geom_violin(fill = "lightblue") +
  scale_y_log10(breaks = c(0, 1.25, 2.5, 5, 10, 20, 40, 80, 160, 320, 640, 1280)) +
  labs(
    title = "Violin Plot of Routing Duration (Log Scale)",
    x = "",
    y = "Routing Duration (ms, log scale)"
  ) +
  theme_minimal() +
  theme(
    axis.title = element_text(size = 21),
    axis.text = element_text(size = 18),
    plot.title = element_text(size = 24)
  )

# ========================

bin_width_s <- 400

# Plot a histogram of routing duration
p <- ggplot(experienced_plans, aes(x = end_time / 3600)) +
  geom_histogram(bins = 36 * 60 * 60 * 1 / bin_width_s) +
  labs(
    title = paste0("Histogram of PT Requests (based on experienced plans, bin width: ", bin_width_s, "s)"),
    x = "Time of the day (h)",
    y = "Count"
  ) +
  theme_minimal() +
  theme(
    axis.title = element_text(size = 21),
    axis.text = element_text(size = 18),
    plot.title = element_text(size = 24)
  )
print(p)
ggsave(paste0("histogram-request-time_", bin_width_s, ".png"), plot = p, width = 15, height = 8, dpi = 400)

# print number of end times
cat("Number of end times:", length(experienced_plans$end_time), "\n")