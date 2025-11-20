library(data.table)
library(ggplot2)
library(scales)
library(dplyr)
source("src/main/R/utils.R")

# 1. List all matching files in the directory
router_path <- "/Users/paulh/hlrn-cluster/rust-pt-routing/parallel-qsim-berlin/output/v6.4/1pct-192/instrument"
files <- list.files(router_path, pattern = "^routing_process_[0-9]+\\.csv$", full.names = TRUE)

# 2. Read each file, attach rank from filename, ensure 'rank' is first column
dt_list <- lapply(files, function(f) {
  # extract number from filename
  rank_val <- as.integer(sub("^routing_process_([0-9]+)\\.csv$", "\\1", basename(f)))

  # log the rank being processed
  message("Processing rank: ", rank_val)

  # read CSV
  dt <- fread(f)

  # add rank column
  dt[, rank := rank_val]

  # make rank the first column
  setcolorder(dt, c("rank", setdiff(names(dt), "rank")))

  dt
})

# 3. Bind all into one big data.table
all_routing <- rbindlist(dt_list, use.names = TRUE, fill = TRUE)

# if request_uuid == -1 no request was processed, remove these rows
all_routing <- all_routing %>% filter(request_uuid != -1)

# Quick sanity check
str(all_routing)
head(all_routing %>% filter(duration == 0))

# rank as a factor so ggplot uses discrete x-axis
all_routing[, rank := factor(rank)]
all_routing[, func_name := factor(func_name, levels = c("call_router", "replace_route", "blocking_recv", "replace_next_trip"))]

ggplot(all_routing, aes(x = func_name, y = duration)) +
  geom_violin() +
  scale_y_log10(
    breaks = scales::log_breaks(n = 10),
    # labels = scales::label_log()
  ) +
  theme_increase_all_text() +
  labs(
    title = paste("Duration per rank at ", router_path),
    x = "Function",
    y = "Duration in ns"
  )

# group all_routing by request_uuid, put func_name as columns <func_name>_duration with duration as values, <func_name>_sim_time with sim_time as values, <func_name>_timestamp as values
# Preserve rank, target, person_id columns.
all_routing_wide <- all_routing %>%
  select(timestamp, rank, request_uuid, func_name, duration, sim_time, target, person_id) %>%
  pivot_wider(
    names_from = func_name,
    values_from = c(duration, sim_time, timestamp),
    names_glue = "{func_name}_{.value}"
  )

events <- bind_rows(
  all_routing_wide %>% transmute(time_ns = call_router_timestamp, delta = 1L),
  all_routing_wide %>% transmute(time_ns = replace_route_timestamp + replace_route_duration, delta = -1L)
) %>%
  arrange(time_ns) %>%
  mutate(active = cumsum(delta))

ggplot(events, aes(x = time_ns, y = active)) +
  geom_point(alpha = 0.1) +
  scale_x_continuous(labels = scales::scientific) +
  labs(
    x = "Time (ns)",
    y = "Active requests",
    title = "System Concurrency Over Time @ QSim"
  ) +
  theme_minimal()

# plot sim_time on x axis and duration of blocking_recv on y axis
ggplot(all_routing_wide, aes(x = blocking_recv_sim_time, y = blocking_recv_duration / 1e6)) +
  geom_point(alpha = 0.1) +
  scale_x_continuous(labels = scales::scientific) +
  scale_y_log10(
    # breaks = scales::log_breaks(n = 10),
    # labels = scales::label_log()
  ) +
  theme_increase_all_text() +
  labs(
    title = paste("Blocking recv duration over simulation time"),
    x = "Simulation time",
    y = "Blocking recv duration (ms)"
  )

# show quantiles
h <- all_routing_wide %>%
  # mutate(preplanning_horizon = replace_route_sim_time - call_router_sim_time) %>%
  filter(is.na(replace_route_sim_time)) %>%
  head()

hh <- all_routing %>%
  filter(request_uuid == "2131891618244901985812870262679929708")

ggplot(all_routing_wide %>% mutate(preplanning_horizon = replace_route_sim_time - call_router_sim_time), aes(x = factor(1), y = preplanning_horizon)) +
  geom_violin(quantiles.linetype = 1L) +
  theme_increase_all_text() +
  labs(
    title = paste("Replace route duration over pre-planning horizon"),
    x = "Sim Time",
    y = "Preplanning Horizon"
  )


# ==== Read router data =====
# with header thread,now,departure_time,from,to,start,duration_ns,travel_time_s,request_id
router_path <- "/Users/paulh/hlrn-cluster/rust-pt-routing/parallel-qsim-berlin/output/v6.4/1pct/routing/routing-profiling-2025-11-18_10-50-16.csv"
router_data <- fread(router_path)

# join router_data and all_routing on request_id and request_uuid
setnames(router_data, "request_id", "request_uuid")
combined_data <- data.table::merge.data.table(all_routing_wide, router_data, by = "request_uuid", suffixes = c("_qsim", "_router"))
str(combined_data)

# plot now on x axis and duration_ns from router_data on y axis
ggplot(combined_data, aes(x = now, y = duration_ns / 1e6)) +
  geom_point(alpha = 0.1) +
  theme_increase_all_text() +
  labs(
    title = paste("Router duration over time"),
    x = "Now",
    y = "Router duration in ms"
  )

ggplot(combined_data %>%
         mutate(round_trip_duration_qsim = blocking_recv_timestamp + blocking_recv_duration - call_router_timestamp) %>%
         mutate(latency = round_trip_duration_qsim - duration_ns), aes(x = now, y = latency / 1e6)) +
  geom_point(alpha = 0.1) +
  scale_y_log10() +
  theme_increase_all_text() +
  labs(
    title = paste("End-to-end latency over time"),
    x = "Sim Time",
    y = "Latency in ms"
  ) +
  annotate("text", 30000, 0.5, label = "lowest values are probably depict true latencies\n because for higher, the qsim time is included.\n But would need to measure it without asynchronicity.", color = "red")
