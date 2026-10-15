"""Writes all figures of iterations-vs-dsim-2026 as PDF and PNG.

    cd src/main/python && uv run --group analysis python -m iterations [--out DIR] [--data DIR]
"""
import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from .load import DATA_ROOT, load_phases, load_runs, phase_summary, rtr_summary  # noqa: E402
from .plots import OUT_DIR, phase_shares, rtr_vs_parts, save, scoring_overhead  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=DATA_ROOT, help="runs-svn directory with the experiments")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="directory for the figures")
    args = parser.parse_args()

    runs = load_runs(args.data)
    phases = load_phases(runs)
    rtr = rtr_summary(phases)
    shares = phase_summary(phases)
    figures = {
        "rtr_vs_parts": rtr_vs_parts(rtr),
        "phase_shares": phase_shares(shares),
        "scoring_overhead": scoring_overhead(rtr),
    }
    for name, fig in figures.items():
        for path in save(fig, name, args.out):
            print(f"Written {path}")


if __name__ == "__main__":
    main()
