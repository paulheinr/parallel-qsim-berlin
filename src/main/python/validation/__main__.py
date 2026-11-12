"""Writes the figures of the traffic validation rust vs. DSim and QSim (Berlin v7.1) as PDF and PNG.

    cd src/main/python
    uv run --group analysis python -m validation --rust DIR --dsim DIR
    uv run --group analysis python -m validation --experiment validation-it0
    uv run --group analysis python -m validation --experiment validation-it0 --reference qsim-validation-it0

With --rust and --dsim, DIR is the output directory of a run (or the run directory above it): rust with
output_trips.csv.zst, DSim with <runId>.output_trips.csv.zst (or .csv.gz). Prints the per-trip agreement per mode.

With --experiment, every run of an experiment in runs-svn (load.DATA_ROOT) is compared with the run of the same run_id
(ignoring _gsync-on, since the global sync of rust does not change its results) in the reference experiment (--reference, default dsim-<experiment>), e.g. rust or DSim against QSim. The engines come
from the run.env of the runs. The figures of each pair go into a directory named after its setting (e.g. 1pct_kw_pq),
by default below DATA_ROOT/plots/<experiment>_vs_<reference>/ (e.g. validation-it0_vs_dsim-validation-it0), together
with agreement.csv (the agreement of all pairs in one table) and README.md (runs, builds, command). Afterwards
plots/index.html (validation.report) is written anew, a page with the figures of all comparisons.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .load import DATA_ROOT, read_runs, read_trips  # noqa: E402
from . import report  # noqa: E402
from .plots import ENGINES, OUT_DIR, agreement, departures, save, trav_time_ecdf, trip_scatter  # noqa: E402

# Short names of the settings in the directory names of the pairs
TRAFFIC_SHORT = {"queue": "queue", "kinematicWaves": "kw", "withHoles": "holes"}
LINK_SHORT = {"FIFO": "fifo", "PassingQ": "pq"}
# Run parameters that are written into agreement.csv (as far as params.json has them)
PAIR_KEYS = ["pct", "traffic", "link", "seed", "parts", "run_id"]


def pair_id(run_id: str) -> str:
    """The run_id under which a run is paired: without _gsync-on, so that rust runs with global sync (needed by
    schedule-based transit across partitions without a common link) pair with DSim and QSim runs, which have none."""
    return run_id.replace("_gsync-on", "")


def summary(table):
    """Agreement per column and mode as printed table, with the trip counts of its attrs."""
    shown = table.set_index(["column", "mode"]).round({"identical": 4, "median_diff": 1, "mean_diff": 1,
                                                       "rel_mean_diff": 4, "median_abs_diff": 1, "r": 5})
    counts = ", ".join(f"{k} {v}" for k, v in table.attrs.items())
    return f"{shown.to_string()}\n({counts})"


def compare(a: pd.DataFrame, b: pd.DataFrame, out_dir: Path, engines: tuple[str, str] = ("rust", "dsim")
            ) -> pd.DataFrame:
    """Writes the figures of run a against reference b into out_dir and returns their agreement table. engines are
    those of a and b (keys of plots.ENGINES), for the labels and styles."""
    for trips, expected in zip((a, b), engines):
        # the trips file only tells rust from Java (named dsim), so QSim and DSim are not told apart here
        found = trips.attrs["engine"]
        if found != expected and not (found == "dsim" and expected == "qsim"):
            print(f"Warning: {trips.attrs['path']} looks like a {found} run, not {expected}")
    label_a, label_b = (ENGINES[e]["label"] for e in engines)
    figures = {
        "departures": lambda: departures(a, b, label_a, label_b),
        "scatter_trav_time": lambda: trip_scatter(a, b, "trav_time", label_a, label_b),
        "scatter_traveled_distance": lambda: trip_scatter(a, b, "traveled_distance", label_a, label_b),
        "trav_time_ecdf": lambda: trav_time_ecdf(a, b, engines=engines),
    }
    table = agreement(a, b)
    print(f"{label_a} (a) vs. {label_b} (b):\n{summary(table)}\n")
    for name, make in figures.items():
        fig = make()
        for path in save(fig, name, out_dir):
            print(f"Written {path}")
        plt.close(fig)
    return table


def pair_name(run: dict) -> str:
    """Directory name of a pair, e.g. 1pct_kw_pq or 1pct_queue_fifo_seed1."""
    parts = [f"{run['pct']}pct"]
    if pd.notna(run.get("traffic")):
        parts.append(TRAFFIC_SHORT.get(run["traffic"], run["traffic"]))
    if pd.notna(run.get("link")):
        parts.append(LINK_SHORT.get(run["link"], run["link"]))
    if pd.notna(run.get("seed")):
        parts.append(f"seed{int(run['seed'])}")
    return "_".join(parts)


def builds(exp_dir: Path) -> list[str]:
    """Binaries of an experiment and the commits of their repositories, from build_info.json."""
    info = exp_dir / "build_info.json"
    if not info.exists():
        return ["(no build_info.json)"]
    lines = []
    for sha, build in json.loads(info.read_text()).items():
        repos = ", ".join(f"{Path(url).name} {r['commit'][:8]}{' (dirty)' if r.get('dirty') else ''}"
                          for url, r in build.get("repos", {}).items())
        lines.append(f"`{Path(build['binary']).name}` (sha256 {sha[:12]}): {repos}")
    return lines


def readme(experiment: Path, reference: Path, engines: tuple[str, str], pairs: list[tuple[str, str]]) -> str:
    """README.md of the plot directory of an experiment."""
    label_a, label_b = (ENGINES[e]["label"] for e in engines)
    rows = "\n".join(f"| `{name}` | `{run_id}` |" for name, run_id in pairs)
    figures = (f"- `departures`: departures per hour and main mode, {label_a} and {label_b}\n"
               f"- `scatter_trav_time`, `scatter_traveled_distance`: per-trip {label_a} vs. {label_b}, one panel per "
               "main mode\n"
               "- `trav_time_ecdf`: distribution of the travel times per main mode")
    only_a, only_b = (f"only_{e}" for e in engines)
    return f"""# Validation {label_a} vs. {label_b}: {experiment.name} vs. {reference.name}

Written on {date.today().isoformat()} by `python -m validation` (`src/main/python/validation` in
parallel-qsim-berlin):

    cd src/main/python && uv run --group analysis python -m validation {" ".join(sys.argv[1:])}

Every run of `{experiment.name}` ({label_a}, a) is compared with the run of the same run_id in `{reference.name}`
({label_b}, the reference b). Both are in the parent directory of `plots/`.

Builds:

- {label_a}: {"; ".join(builds(experiment))}
- {label_b}: {"; ".join(builds(reference))}

One directory per pair:

| Directory | run_id |
|---|---|
{rows}

Figures in each directory (PDF and PNG):

{figures}

`agreement.csv`: the per-trip agreement of all pairs (`validation.plots.agreement`), one row per pair, column
(trav_time, traveled_distance, dep_time) and main mode (`all`: all common trips), with the run parameters in front.
Differences are a - b in seconds or meters; `rel_mean_diff` = sum of a / sum of b - 1. `{only_a}`, `{only_b}` and
`changed_mode` count the trips per pair that are only in one run or have another main mode.
"""


def experiment_engine(runs: pd.DataFrame, exp_dir: Path) -> str:
    engines = runs["engine"].unique()
    if len(engines) != 1:
        raise SystemExit(f"{exp_dir}: runs of several engines {list(engines)}")
    return engines[0]


def compare_experiments(experiment: Path, reference: Path, out_dir: Path):
    runs, ref_runs = read_runs(experiment), read_runs(reference)
    engines = (experiment_engine(runs, experiment), experiment_engine(ref_runs, reference))
    if engines[0] == engines[1]:
        raise SystemExit(f"Both experiments are {engines[0]} runs")
    ref_paths = dict(zip(ref_runs["run_id"].map(pair_id), ref_runs["path"]))
    missing = sorted(run_id for run_id in runs["run_id"] if pair_id(run_id) not in ref_paths)
    if missing:
        print(f"No run in {reference.name} for {len(missing)} runs, left out: {', '.join(missing)}")
    tables, pairs = [], []
    for run in runs.sort_values(["pct", "run_id"]).to_dict("records"):
        if pair_id(run["run_id"]) not in ref_paths:
            continue
        name = pair_name(run)
        print(f"== {name} ({run['run_id']})")
        table = compare(read_trips(run["path"] / "output"), read_trips(ref_paths[pair_id(run["run_id"])] / "output"),
                        out_dir / name, engines)
        keys = {k: run[k] for k in PAIR_KEYS if k in run and pd.notna(run[k])}
        counts = {f"only_{engines[0]}": table.attrs["only_a"], f"only_{engines[1]}": table.attrs["only_b"],
                  "changed_mode": table.attrs["changed_mode"]}
        tables.append(table.assign(pair=name, **keys, **counts))
        pairs.append((name, run["run_id"]))
    if not tables:
        raise SystemExit("No pairs found")
    result = pd.concat(tables, ignore_index=True)
    front = ["pair"] + [k for k in PAIR_KEYS if k in result]
    result = result[front + [c for c in result.columns if c not in front]]
    result.to_csv(out_dir / "agreement.csv", index=False)
    (out_dir / "README.md").write_text(readme(experiment, reference, engines, pairs))
    print(f"Written {out_dir / 'agreement.csv'} and README.md ({len(pairs)} pairs)")
    if out_dir.parent == report.PLOTS_DIR:
        print(f"Written {report.write()} (all comparisons)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rust", type=Path, help="output directory of the rust run")
    parser.add_argument("--dsim", type=Path, help="output directory of the DSim run")
    parser.add_argument("--experiment", type=Path, help="rust experiment (name below DATA_ROOT or directory)")
    parser.add_argument("--reference", type=Path, help="reference experiment, e.g. qsim-validation-it0 "
                                                       "(default: dsim-<experiment>)")
    parser.add_argument("--out", type=Path, help="directory for the figures (default: OUT_DIR for single runs, "
                                                 "DATA_ROOT/plots/<experiment>_vs_<reference> for experiments)")
    args = parser.parse_args()

    if args.experiment:
        if args.rust or args.dsim:
            parser.error("--experiment cannot be combined with --rust/--dsim")
        experiment = args.experiment if args.experiment.is_dir() else DATA_ROOT / args.experiment
        reference = args.reference or Path(f"dsim-{experiment.name}")
        reference = reference if reference.is_dir() else DATA_ROOT / reference
        out = args.out or DATA_ROOT / "plots" / f"{experiment.name}_vs_{reference.name}"
        compare_experiments(experiment, reference, out)
    elif args.rust and args.dsim:
        compare(read_trips(args.rust), read_trips(args.dsim), args.out or OUT_DIR)
    else:
        parser.error("give --rust and --dsim, or --experiment")


if __name__ == "__main__":
    main()
