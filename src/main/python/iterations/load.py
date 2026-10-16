"""Loads the profiling experiments of iterations-vs-dsim-2026 (rust and DSim) from the runs-svn working copy.

    runs = load_runs()          # one row per run: engine, pct, parts, method, scoring, events, rep, Slurm state
    phases = load_phases(runs)  # one row per run, iteration and phase: wall time in seconds

Phases (wall time per iteration, all with millisecond resolution or better):

    mobsim      the simulation loop. rust: span `simulation::run` of rank 0 (all ranks are synchronized every time
                step). DSim: from "Starting Simulation" to the "Real-time-ratio" line in the logfile.
    scoring     rust: `run_scoring_phase`. DSim: scoring event -> all scoring listeners called.
    replanning  the replanning that prepares the plans of this iteration. rust logs it at the end of the previous
                iteration (`run_replanning_phase` of iteration - 1), DSim at the beginning of this one.
    other       the rest of the iteration: iteration wall time - mobsim - scoring - replanning (rust: from the
                start of this replanning to the start of the next one, DSim: ITERATION BEGINS -> ENDS).

Iteration 0 has no replanning and includes the setup, so `steady` (iterations 1..8) excludes it. Iteration 9 has no
complete wall time in rust, because nothing follows it.

The real-time ratio is simulated seconds / mobsim seconds. rust: (end_time - start_time) of output_config.yml.
DSim: the ratio it logs itself, measured over the same simulation loop.
"""
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_ROOT = Path.home() / "runs-svn/matsim-rust/iterations-vs-dsim-2026"
EXPERIMENTS = ["scaling-v2", "dsim-scaling"]  # scaling: rust before the mobsim optimizations (matsim-rust 6960b40)
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
        df["engine"] = [engine(root / experiment / d) for d in df["run_dir"]]
        df["path"] = [root / experiment / d for d in df["run_dir"]]
        frames.append(df)
    runs = pd.concat(frames, ignore_index=True)
    for column in ("scoring", "events"):
        runs[column] = runs[column].astype(str).str.lower().map({"true": True, "false": False})
    failed = runs[(runs["exit_code"] != 0) | (runs["slurm_state"] != "COMPLETED")]
    if len(failed):
        print(f"Ignoring {len(failed)} runs that did not complete: {', '.join(failed['run_id'])}")
    return runs.drop(failed.index).reset_index(drop=True)


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
    keys = ["experiment", "run_id", "engine", "pct", "parts", "method", "scoring", "events", "rep"]
    return runs[keys].merge(phases, on=["experiment", "run_id"])


def rust_phases(output: Path) -> pd.DataFrame:
    instrument = output / "instrument"
    mobsim = pd.read_csv(instrument / "instrument_process_0.csv")
    controller = pd.read_csv(instrument / "instrument_process_controller.csv")
    simulated = simulated_seconds(output / "output_config.yml")

    mobsim = mobsim[mobsim["func_name"] == "run"].set_index("iteration")
    scoring = controller[controller["func_name"] == "run_scoring_phase"].set_index("iteration")
    replanning = controller[controller["func_name"] == "run_replanning_phase"].set_index("iteration")
    replanning_start = (replanning["timestamp"] - replanning["duration_ns"]) / 1e9

    rows = []
    for iteration in mobsim.index:
        row = {"iteration": iteration,
               "mobsim": mobsim.at[iteration, "duration_ns"] / 1e9,
               "scoring": scoring["duration_ns"].get(iteration, 0) / 1e9}
        if iteration - 1 in replanning.index:
            row["replanning"] = replanning.at[iteration - 1, "duration_ns"] / 1e9
            if iteration in replanning.index:
                wall = replanning_start[iteration] - replanning_start[iteration - 1]
                row["other"] = wall - row["mobsim"] - row["scoring"] - row["replanning"]
        row["rtr"] = simulated / row["mobsim"]
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
    keys = ["experiment", "run_id", "engine", "pct", "parts", "method", "scoring", "events", "rep"]
    mobsim = phases[(phases["phase"] == "mobsim") & phases["iteration"].isin(iterations)]
    return (mobsim.groupby(keys)["rtr"].agg(rtr="median", rtr_min="min", rtr_max="max", iterations="count")
            .reset_index())


def phase_summary(phases: pd.DataFrame) -> pd.DataFrame:
    """Median seconds per phase over the steady iterations, one row per run and phase, with the share per run."""
    keys = ["experiment", "run_id", "engine", "pct", "parts", "method", "scoring", "events", "rep"]
    df = steady(phases).groupby(keys + ["phase"])["seconds"].median().reset_index()
    df["share"] = df["seconds"] / df.groupby(keys)["seconds"].transform("sum")
    return df
