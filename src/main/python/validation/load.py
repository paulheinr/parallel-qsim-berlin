"""Loads the trips of rust (matsim-rust) and Java DSim runs of Berlin v7.1 for the validation of the traffic (also
MATSim QSim runs, which write the same files as DSim).

    trips = read_trips(output_dir)        # one run: one row per trip, times in seconds
    trips = read_experiment("validation-it0")  # all runs of an experiment, with the run parameters and engine

Both engines write the MATSim trips file (semicolon separated, times as HH:MM:SS, also beyond 24:00:00): rust
`output_trips.csv.zst`, DSim `<runId>.output_trips.csv.zst` (older Java runs `.csv.gz`). Experiments from the cluster
are in runs-svn below DATA_ROOT, one directory per run in `runs/<run_id>/` with `params.json` and the outputs in
`output/` (see scripts/cluster/README.md). rust experiments are named `validation-*`, DSim ones `dsim-validation-*`, QSim ones `qsim-validation-*`.
"""
import json
import re
from pathlib import Path

import pandas as pd

DATA_ROOT = Path.home() / "runs-svn/matsim-rust/iterations-vs-dsim-2026"
TIME_COLUMNS = ["dep_time", "trav_time", "wait_time"]
# Read as text: ids may look like numbers (or be "null" in every row), which would turn them into floats
ID_COLUMNS = ["person", "trip_id", "start_facility_id", "start_link", "end_facility_id", "end_link",
              "first_pt_boarding_stop", "last_pt_egress_stop"]
# Columns that identify a run in read_experiment, from params.json (traffic, link and seed only in validation runs)
RUN_KEYS = ["experiment", "run_id", "engine", "pct", "parts", "method", "scoring", "events", "global_sync", "rep",
            "traffic", "link", "seed"]

_RUST_TRIPS = "output_trips.csv.zst"
_DSIM_TRIPS = ["*.output_trips.csv.zst", "*.output_trips.csv.gz"]


def trips_file(output_dir: Path) -> tuple[Path, str]:
    """The trips file of a run output directory and the engine that wrote it (rust or dsim). Also accepts the run
    directory above `output/`."""
    output_dir = Path(output_dir)
    for directory in (output_dir, output_dir / "output"):
        if (directory / _RUST_TRIPS).exists():
            return directory / _RUST_TRIPS, "rust"
        for pattern in _DSIM_TRIPS:
            if found := sorted(directory.glob(pattern)):
                if len(found) > 1:
                    raise ValueError(f"{directory}: more than one trips file: {[f.name for f in found]}")
                return found[0], "dsim"
    raise FileNotFoundError(f"No trips file in {output_dir} (rust {_RUST_TRIPS}, DSim {', '.join(_DSIM_TRIPS)})")


def seconds(times: pd.Series) -> pd.Series:
    """HH:MM:SS (hours may exceed 24) -> seconds. Empty values stay NaN."""
    parts = times.str.split(":", expand=True).astype(float)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def read_trips(output_dir: Path) -> pd.DataFrame:
    """Trips of one run: one row per trip as in the trips file, with dep_time, trav_time and wait_time in seconds
    and the arrival time `arr_time` = dep_time + trav_time. The attribute `engine` of the frame says which engine wrote
    it (`trips.attrs["engine"]`)."""
    path, engine = trips_file(output_dir)
    trips = pd.read_csv(path, sep=";", dtype={c: str for c in ID_COLUMNS}, keep_default_na=False,
                        na_values={c: [""] for c in TIME_COLUMNS})
    for column in TIME_COLUMNS:
        trips[column] = seconds(trips[column])
    trips["arr_time"] = trips["dep_time"] + trips["trav_time"]
    trips.attrs.update(engine=engine, path=str(path))
    return trips


def engine(run_dir: Path) -> str:
    """The ENGINE of run.env (dsim or qsim), rust if run.env exists without it; otherwise from the name of the trips
    file (rust, or dsim for any Java run)."""
    env = run_dir / "run.env"
    if env.exists():
        found = re.search(r"^ENGINE=['\"]?(\w+)", env.read_text(), re.MULTILINE)
        return found.group(1) if found else "rust"
    return trips_file(run_dir / "output")[1]


def read_runs(exp_dir: Path) -> pd.DataFrame:
    """One row per run of an experiment directory: the parameters of params.json, engine and path of the run. Runs
    that runs.csv (written by `collect`) lists as failed are left out."""
    exp_dir = Path(exp_dir)
    rows = []
    for params in sorted(exp_dir.glob("runs/*/params.json")):
        row = json.loads(params.read_text())
        row.setdefault("experiment", exp_dir.name)
        row["engine"] = engine(params.parent)
        row["path"] = params.parent
        rows.append(row)
    if not rows:
        raise FileNotFoundError(f"No runs/*/params.json in {exp_dir}")
    runs = pd.DataFrame(rows)
    if (exp_dir / "runs.csv").exists():
        status = pd.read_csv(exp_dir / "runs.csv")
        failed = status[(status["exit_code"] != 0) | (status["slurm_state"] != "COMPLETED")]["run_id"]
        if len(failed):
            print(f"Ignoring {len(failed)} runs that did not complete: {', '.join(failed)}")
        runs = runs[~runs["run_id"].isin(failed)].reset_index(drop=True)
    return runs


def read_experiment(exp_dir: Path | str, root: Path = DATA_ROOT) -> pd.DataFrame:
    """Trips of all runs of an experiment, one row per run and trip, with the run parameters (RUN_KEYS, as far as
    params.json has them) in front. exp_dir is a directory or the name of an experiment below root."""
    exp_dir = Path(exp_dir)
    if not exp_dir.is_absolute() and not exp_dir.exists():
        exp_dir = root / exp_dir
    runs = read_runs(exp_dir)
    keys = [k for k in RUN_KEYS if k in runs]
    frames = []
    for run in runs.to_dict("records"):
        trips = read_trips(run["path"] / "output")
        frames.append(trips.assign(**{k: run[k] for k in keys})[keys + list(trips.columns)])
    return pd.concat(frames, ignore_index=True)


def runs_of(trips: pd.DataFrame, **params) -> dict[str, pd.DataFrame]:
    """Splits the trips of read_experiment into one frame per run, keyed by run_id, optionally only the runs with
    the given parameters (e.g. engine="dsim", seed=1)."""
    selected = trips
    for key, value in params.items():
        selected = selected[selected[key] == value]
    runs = {}
    for run_id, g in selected.groupby("run_id", sort=True):
        g = g.reset_index(drop=True)
        g.attrs = {"engine": g["engine"].iloc[0], "run": f"{g['experiment'].iloc[0]}/{run_id}"}
        runs[run_id] = g
    return runs
