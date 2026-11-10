"""Writes the figures of the traffic validation rust vs. DSim (Berlin v7.1) as PDF and PNG.

    cd src/main/python && uv run --group analysis python -m validation --rust DIR --dsim DIR

DIR is the output directory of a run (or the run directory above it): rust with output_trips.csv.zst, DSim with
<runId>.output_trips.csv.zst (or .csv.gz). Also prints the per-trip agreement per mode.
"""
import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from .load import read_trips  # noqa: E402
from .plots import OUT_DIR, agreement, departures, save, trav_time_ecdf, trip_scatter  # noqa: E402


def summary(table):
    """Agreement per column and mode as printed table, with the trip counts of its attrs."""
    shown = table.set_index(["column", "mode"]).round({"identical": 4, "median_diff": 1, "mean_diff": 1,
                                                       "median_abs_diff": 1, "r": 5})
    counts = ", ".join(f"{k} {v}" for k, v in table.attrs.items())
    return f"{shown.to_string()}\n({counts})"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rust", type=Path, required=True, help="output directory of the rust run")
    parser.add_argument("--dsim", type=Path, required=True, help="output directory of the DSim run")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="directory for the figures")
    args = parser.parse_args()

    rust, dsim = read_trips(args.rust), read_trips(args.dsim)
    for trips, expected in ((rust, "rust"), (dsim, "dsim")):
        if trips.attrs["engine"] != expected:
            print(f"Warning: {trips.attrs['path']} looks like a {trips.attrs['engine']} run, not {expected}")
    figures = {
        "departures": departures(rust, dsim),
        "scatter_trav_time": trip_scatter(rust, dsim, "trav_time"),
        "scatter_traveled_distance": trip_scatter(rust, dsim, "traveled_distance"),
        "trav_time_ecdf": trav_time_ecdf(rust, dsim),
    }
    print(f"Rust (a) vs. DSim (b):\n{summary(agreement(rust, dsim))}\n")
    for name, fig in figures.items():
        for path in save(fig, name, args.out):
            print(f"Written {path}")


if __name__ == "__main__":
    main()
