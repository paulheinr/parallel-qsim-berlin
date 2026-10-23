"""Loads the profiling experiments of iterations-vs-dsim-2026 (rust and DSim) from the runs-svn working copy.

    runs = load_runs()          # one row per run: engine, the grid keys (pct, ..., global_sync), rep, Slurm state
    phases = load_phases(runs)  # one row per run, iteration and phase: wall time in seconds

Phases (wall time per iteration, all with millisecond resolution or better):

    mobsim      rust: span `run_mobsim_phase` of the controller, the whole mobsim phase including starting and stopping
                the simulation processes (about 1 s more than the loop at 10 %). Runs before matsim-rust d41dba8 (e.g.
                scaling) do not have it and use the loop `simulation::run` of rank 0 instead. DSim: the simulation
                loop, from "Starting Simulation" to the "Real-time-ratio" line in the logfile.
    scoring     rust: `run_scoring_phase`. DSim: scoring event -> all scoring listeners called.
    replanning  the replanning that prepares the plans of this iteration. rust logs it at the end of the previous
                iteration (`run_replanning_phase` of iteration - 1), DSim at the beginning of this one.
    other       the rest of the iteration: iteration wall time - mobsim - scoring - replanning (rust: from the
                start of this replanning to the start of the next one, DSim: ITERATION BEGINS -> ENDS).

Iteration 0 has no replanning and includes the setup, so `steady` (iterations 1..8) excludes it. Iteration 9 has no
complete wall time in rust, because nothing follows it.

With `run_mobsim_phase`, the phases of rust follow each other without gaps, so `other` is close to 0 there.

The real-time ratio is simulated seconds / seconds of the simulation loop. rust: (end_time - start_time) of
output_config.yml / span `simulation::run` of rank 0 (all ranks are synchronized every time step). DSim: the ratio it
logs itself, measured over its simulation loop.
"""
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_ROOT = Path.home() / "runs-svn/matsim-rust/iterations-vs-dsim-2026"
# rust (matsim-rust c646f29c, PR #328) and DSim on the same networks metis-minconn-const. On the networks metis:
# scaling-v5 (e20838e) with dsim-scaling, scaling-v4 (eec3c5f, slower with scoring at many partitions, see 3e477073),
# scaling-v3 (f91a7b2), scaling-v2 (d41dba8), scaling (6960b40, before the mobsim optimizations).
EXPERIMENTS = ["scaling-v6", "dsim-scaling-minconn"]
# The same plots 1a and 1b with global sync: all partitions wait at a barrier in every time step (rust only), on the
# networks metis-minconn-const as EXPERIMENTS. On the networks metis: scaling-v5-gsync (e20838e) with dsim-scaling,
# scaling-v4-gsync (eec3c5f), scaling-v3-gsync (f91a7b2, std::sync::Barrier instead of the spin-then-park barrier).
GSYNC_EXPERIMENTS = ["scaling-v6-gsync", "dsim-scaling-minconn"]
# Columns that identify a run. setting only describes the experiment (name and library version, for the figures).
RUN_KEYS = ["experiment", "setting", "run_id", "engine", "pct", "parts", "method", "scoring", "events", "global_sync",
            "rep"]
PHASES = ["mobsim", "scoring", "replanning", "other"]
STEADY = range(1, 9)

_DSIM_MARKERS = {
    "begin": re.compile(r"### ITERATION (\d+) BEGINS"),
    "starts_done": re.compile(r"\[it\.(\d+)\] all ControllerIterationStartsListeners called"),
    "replanning_done": re.compile(r"\[it\.(\d+)\] all ControllerReplanningListeners called"),
    "scoring": re.compile(r"### ITERATION (\d+) fires scoring event"),
    "scoring_done": re.compile(r"\[it\.(\d+)\] all ControllerScoringListeners called"),
    "end": re.compile(r"### ITERATION (\d+) ENDS"),
}
_DSIM_SIM_START = re.compile(r"Starting Simulation at")
_DSIM_SIM_END = re.compile(r"Real-time-ratio: ([0-9.]+)")


def load_runs(root: Path = DATA_ROOT, experiments: list[str] = EXPERIMENTS) -> pd.DataFrame:
    """runs.csv of all experiments, completed runs only."""
    frames = []
    for experiment in experiments:
        df = pd.read_csv(root / experiment / "runs.csv")
        df.insert(0, "experiment", experiment)
        df.insert(1, "setting", setting(root / experiment))
        df["engine"] = [engine(root / experiment / d) for d in df["run_dir"]]
        df["path"] = [root / experiment / d for d in df["run_dir"]]
        frames.append(df)
    runs = pd.concat(frames, ignore_index=True)
    if "global_sync" not in runs:
        runs["global_sync"] = False  # runs.csv of collect before global_sync was a grid key
    runs["global_sync"] = runs["global_sync"].fillna(False)
    for column in ("scoring", "events", "global_sync"):
        runs[column] = runs[column].astype(str).str.lower().map({"true": True, "false": False})
    failed = runs[(runs["exit_code"] != 0) | (runs["slurm_state"] != "COMPLETED")]
    if len(failed):
        print(f"Ignoring {len(failed)} runs that did not complete: {', '.join(failed['run_id'])}")
    return runs.drop(failed.index).reset_index(drop=True)


def setting(experiment_dir: Path) -> str:
    """Name of the experiment with the library versions of its binaries from build_info.json, e.g.
    "scaling-v4 (matsim-rust eec3c5f)". Before 2026-10-15, build_info.json did not record matsim-rust, so older rust
    experiments have the name only. The DSim jar has the matsim-berlin commit in its file name; build_info.json also lists
    the matsim-rust of the cluster repo for it, which DSim does not use."""
    info = experiment_dir / "build_info.json"
    versions = []
    for binary in (json.loads(info.read_text()).values() if info.exists() else []):
        if m := re.search(r"-g([0-9a-f]{7,})\.jar$", binary["binary"]):
            libraries = [f"matsim-berlin {m.group(1)[:7]}"]
        else:
            # e.g. https://github.com/matsim-vsp/matsim-rust?branch=main-mode-neighbors -> matsim-rust
            repos = {url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]: repo["commit"][:7]
                     for url, repo in binary["repos"].items()}
            libraries = [f"{name} {commit}" for name, commit in repos.items() if name != "parallel-qsim-berlin"]
        versions += [v for v in libraries if v not in versions]
    return f"{experiment_dir.name} ({', '.join(versions)})" if versions else experiment_dir.name


def engine(run_dir: Path) -> str:
    """dsim if run.env sets ENGINE=dsim, otherwise rust."""
    env = (run_dir / "run.env").read_text()
    return "dsim" if re.search(r"^ENGINE=['\"]?dsim", env, re.MULTILINE) else "rust"


def load_phases(runs: pd.DataFrame) -> pd.DataFrame:
    """Wall time per run, iteration and phase in seconds, with the real-time ratio of the mobsim."""
    frames = []
    for run in runs.itertuples():
        reader = rust_phases if run.engine == "rust" else dsim_phases
        df = reader(run.path / "output")
        df.insert(0, "run_id", run.run_id)
        df.insert(0, "experiment", run.experiment)
        frames.append(df)
    phases = pd.concat(frames, ignore_index=True)
    return runs[RUN_KEYS].merge(phases, on=["experiment", "run_id"])


def rust_phases(output: Path) -> pd.DataFrame:
    instrument = output / "instrument"
    mobsim = pd.read_csv(instrument / "instrument_process_0.csv")
    controller = pd.read_csv(instrument / "instrument_process_controller.csv")
    simulated = simulated_seconds(output / "output_config.yml")

    loop = mobsim[mobsim["func_name"] == "run"].set_index("iteration")["duration_ns"] / 1e9
    phase = controller[controller["func_name"] == "run_mobsim_phase"].set_index("iteration")["duration_ns"] / 1e9
    mobsim = phase if len(phase) else loop
    scoring = controller[controller["func_name"] == "run_scoring_phase"].set_index("iteration")
    replanning = controller[controller["func_name"] == "run_replanning_phase"].set_index("iteration")
    replanning_start = (replanning["timestamp"] - replanning["duration_ns"]) / 1e9

    rows = []
    for iteration in loop.index:
        row = {"iteration": iteration,
               "mobsim": mobsim[iteration],
               "scoring": scoring["duration_ns"].get(iteration, 0) / 1e9}
        if iteration - 1 in replanning.index:
            row["replanning"] = replanning.at[iteration - 1, "duration_ns"] / 1e9
            if iteration in replanning.index:
                wall = replanning_start[iteration] - replanning_start[iteration - 1]
                row["other"] = wall - row["mobsim"] - row["scoring"] - row["replanning"]
        row["rtr"] = simulated / loop[iteration]
        rows.append(row)
    return to_long(rows)


def simulated_seconds(config: Path) -> float:
    text = config.read_text()
    start = re.findall(r"^\s+start_time: (\d+)", text, re.MULTILINE)
    end = re.findall(r"^\s+end_time: (\d+)", text, re.MULTILINE)
    if len(start) != 1 or len(end) != 1:
        raise ValueError(f"{config}: expected one start_time and end_time, found {start} and {end}")
    return float(end[0]) - float(start[0])


def dsim_phases(output: Path) -> pd.DataFrame:
    logfile = next(output.glob("*.logfile.log"))
    markers, mobsim, rtr = {}, {}, {}
    iteration, sim_start = None, None
    with open(logfile, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "ITERATION" not in line and "[it." not in line and "Simulation" not in line and "Real-time" not in line:
                continue
            for name, pattern in _DSIM_MARKERS.items():
                if m := pattern.search(line):
                    iteration = int(m.group(1))
                    markers.setdefault(iteration, {})[name] = timestamp(line)
                    break
            else:
                if _DSIM_SIM_START.search(line):
                    sim_start = timestamp(line)
                elif m := _DSIM_SIM_END.search(line):
                    mobsim[iteration] = (timestamp(line) - sim_start).total_seconds()
                    rtr[iteration] = float(m.group(1))

    def seconds(m, start, end):
        return (m[end] - m[start]).total_seconds() if start in m and end in m else None

    rows = []
    for iteration, m in sorted(markers.items()):
        row = {"iteration": iteration, "mobsim": mobsim[iteration], "rtr": rtr[iteration],
               "scoring": seconds(m, "scoring", "scoring_done")}
        if "replanning_done" in m:
            row["replanning"] = seconds(m, "starts_done", "replanning_done")
            row["other"] = seconds(m, "begin", "end") - row["mobsim"] - row["scoring"] - row["replanning"]
        rows.append(row)
    return to_long(rows)


def timestamp(line: str) -> datetime:
    """The log4j timestamp at the start of a logfile line, e.g. 2026-10-15T02:31:19,825."""
    return datetime.strptime(line[:23], "%Y-%m-%dT%H:%M:%S,%f")


def to_long(rows: list[dict]) -> pd.DataFrame:
    """One row per iteration and phase. rtr stays a column (the same for all phases of an iteration)."""
    wide = pd.DataFrame(rows)
    long = wide.melt(id_vars=["iteration", "rtr"], value_vars=[p for p in PHASES if p in wide],
                     var_name="phase", value_name="seconds")
    return long.dropna(subset=["seconds"]).reset_index(drop=True)


def steady(phases: pd.DataFrame) -> pd.DataFrame:
    return phases[phases["iteration"].isin(STEADY)]


def rtr_summary(phases: pd.DataFrame, iterations=range(1, 10)) -> pd.DataFrame:
    """Real-time ratio per run: median, min and max over the given iterations (default 1..9, without the setup)."""
    mobsim = phases[(phases["phase"] == "mobsim") & phases["iteration"].isin(iterations)]
    return (mobsim.groupby(RUN_KEYS)["rtr"].agg(rtr="median", rtr_min="min", rtr_max="max", iterations="count")
            .reset_index())


def phase_summary(phases: pd.DataFrame) -> pd.DataFrame:
    """Median seconds per phase over the steady iterations, one row per run and phase, with the share per run."""
    df = steady(phases).groupby(RUN_KEYS + ["phase"])["seconds"].median().reset_index()
    df["share"] = df["seconds"] / df.groupby(RUN_KEYS)["seconds"].transform("sum")
    return df
