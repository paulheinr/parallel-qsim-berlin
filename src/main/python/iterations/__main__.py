"""Writes all figures of iterations-vs-dsim-2026 as PDF and PNG.

    cd src/main/python && uv run --group analysis python -m iterations [--out DIR] [--data DIR] [--experiments ...]

Older rust runs: --experiments scaling-v2 dsim-scaling, or scaling (before the mobsim optimizations). Plots 1a and 1b
are also written with global sync (--gsync-experiments, files *_gsync), if these experiments are in --data.
"""
import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from .load import (DATA_ROOT, EXPERIMENTS, GSYNC_EXPERIMENTS, load_phases, load_runs, phase_summary,  # noqa: E402
                   rtr_summary)
from .plots import OUT_DIR, phase_lines, rtr_no_agents, rtr_vs_parts, save, scoring_overhead  # noqa: E402

GSYNC_LABELS = {"rust": "Rust, global sync"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=DATA_ROOT, help="runs-svn directory with the experiments")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="directory for the figures")
    parser.add_argument("--experiments", nargs="+", default=EXPERIMENTS, help="experiments below --data")
    parser.add_argument("--gsync-experiments", nargs="+", default=GSYNC_EXPERIMENTS,
                        help="experiments for plots 1a and 1b with global sync")
    args = parser.parse_args()

    runs = load_runs(args.data, args.experiments)
    phases = load_phases(runs)
    rtr = rtr_summary(phases)
    medians = phase_summary(phases)
    figures = {
        "rtr_no_agents": rtr_no_agents(rtr),
        "rtr_vs_parts": rtr_vs_parts(rtr),
        "phase_lines": phase_lines(medians),
        "scoring_overhead": scoring_overhead(rtr),
    }

    missing = [e for e in args.gsync_experiments if not (args.data / e / "runs.csv").exists()]
    if missing:
        print(f"Not in {args.data}: {', '.join(missing)}, no figures with global sync.")
    else:
        gsync = rtr_summary(load_phases(load_runs(args.data, args.gsync_experiments)))
        figures["rtr_no_agents_gsync"] = rtr_no_agents(gsync, GSYNC_LABELS)
        figures["rtr_vs_parts_gsync"] = rtr_vs_parts(gsync, GSYNC_LABELS)

    for name, fig in figures.items():
        for path in save(fig, name, args.out):
            print(f"Written {path}")


if __name__ == "__main__":
    main()
