#!/usr/bin/env python3
"""Submit profiling experiments of berlin_iterations_v7 to Slurm and collect their results.

    uv run scripts/cluster/cluster.py submit experiments/example.toml --dry-run
    uv run scripts/cluster/cluster.py submit experiments/example.toml --only pct=1
    uv run scripts/cluster/cluster.py collect example
    uv run scripts/cluster/cluster.py fetch example      # locally: collect on the cluster, copy results into runs-svn

Paths and Slurm settings are read from scripts/cluster/cluster.toml. The same runs with DSim (Java) use
--settings scripts/cluster/cluster-dsim.toml. See scripts/cluster/README.md.
"""
import sys

if sys.version_info < (3, 11):
    sys.exit("cluster.py needs Python >= 3.11 (tomllib), run it with `uv run scripts/cluster/cluster.py`.")

import argparse
import csv
import datetime
import hashlib
import itertools
import json
import re
import shlex
import shutil
import subprocess
import tempfile
import textwrap
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[1]
RUN_SCRIPT = SCRIPT_DIR / "run-sim.sh"
GRID_KEYS = ("pct", "parts", "method", "scoring", "events", "global_sync", "traffic", "link", "seed")
# Grid keys that a [[grid]] block may leave out, with their value then. Runs with the default have the same run id as
# before the key was added.
GRID_DEFAULTS = {"global_sync": [False], "traffic": [None], "link": [None], "seed": [None]}
# Grid keys whose default None passes nothing, so the value of the config applies. Only runs that set them have them
# in params.json, and runs.csv only has their columns if a run sets them.
OPTIONAL_KEYS = ("traffic", "link", "seed")
# Allowed values of traffic and link in MATSim's spelling (DSim needs it, rust ignores the case) with their short form
# in run ids. Both forms (in any case) are accepted in experiment definitions and by --only.
TRAFFIC_DYNAMICS = {"queue": "queue", "kinematicWaves": "kw"}
LINK_DYNAMICS = {"FIFO": "fifo", "PassingQ": "pq"}
SHORT_NAMES = {"traffic": TRAFFIC_DYNAMICS, "link": LINK_DYNAMICS}
# Keys of an experiment definition. config, run_env and extra_args are applied on top of the settings.
EXPERIMENT_KEYS = {"name", "comment", "grid", "repetitions", "iterations", "time_limit", "config", "run_env",
                   "extra_args"}
# run_env variables whose file is copied into <exp>/<directory>/<sha12>/ like the binary, so that rebuilding it does
# not change queued jobs.
SNAPSHOT_ENV = {"TRIPS_JAR": "trips-jar"}
MANIFEST_FIELDS = ["run_id", "job_id", "submitted_at"]
DESCRIPTION_FILE = "description.md"

# Files that fetch copies into runs-svn, relative to the experiment directory. Everything else (binary snapshots,
# plans, events, networks, ITERS/, per-process logs) stays on the cluster. [fetch] extra_files adds patterns.
FETCH_FILES = [
    DESCRIPTION_FILE, "experiment.*.toml", "build_info.json", "manifest.csv", "runs.csv",
    "runs/*/params.json", "runs/*/run.env", "runs/*/result.json", "runs/*/slurm-*.log", "runs/*/phases.csv",
    # rust
    "runs/*/output/instrument/*", "runs/*/output/output_config.yml", "runs/*/output/logs/log_process_controller.txt",
    # dsim
    "runs/*/output/*.csv", "runs/*/output/*.logfile.log", "runs/*/output/*.logfileWarningsErrors.log",
    "runs/*/output/runtimes-*/runtime-*.csv", "runs/*/output/runtimes-*/*.hgrm",
]


@dataclass(frozen=True)
class Run:
    pct: int
    parts: int
    method: str
    scoring: bool
    events: bool
    global_sync: bool
    rep: int
    traffic: str | None = None    # traffic dynamics, key of TRAFFIC_DYNAMICS
    link: str | None = None       # link dynamics, key of LINK_DYNAMICS
    seed: int | None = None       # random seed

    @property
    def run_id(self) -> str:
        optional = "".join([
            "_gsync-on" if self.global_sync else "",
            f"_traffic-{TRAFFIC_DYNAMICS[self.traffic]}" if self.traffic is not None else "",
            f"_link-{LINK_DYNAMICS[self.link]}" if self.link is not None else "",
            f"_seed-{self.seed}" if self.seed is not None else "",
        ])
        return (f"{self.pct}pct_{self.method}_p{self.parts:03d}"
                f"_score-{on_off(self.scoring)}_events-{on_off(self.events)}{optional}_r{self.rep}")

    def params(self) -> dict:
        values = {key: getattr(self, key) for key in GRID_KEYS}
        return {k: v for k, v in values.items() if not (k in OPTIONAL_KEYS and v is None)} | {"rep": self.rep}

    def sort_key(self) -> tuple:
        return (self.pct, self.method, self.parts, not self.scoring, self.events, self.global_sync,
                self.traffic or "", self.link or "", -1 if self.seed is None else self.seed, self.rep)


def on_off(value: bool) -> str:
    return "on" if value else "off"


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ----------------------------------------------------------------------
# Settings and experiment definition
# ----------------------------------------------------------------------

class Settings:
    def __init__(self, path: Path):
        with open(path, "rb") as f:
            s = tomllib.load(f)
        self.out_root_setting = s["out_root"]
        self.out_root = resolve(s["out_root"])
        self.partitions_root = resolve(s["partitions_root"])
        self.version = s["scenario_version"]
        self.config_pattern = s["config_pattern"]
        self.network_pattern = s["network_pattern"]
        self.binary = newest(resolve(s["binary"]))
        self.run_env = s.get("run_env", {})
        self.slurm = s.get("slurm", {})
        self.fetch = s.get("fetch", {})
        # [pct.<n>] replaces config_pattern and single [run_env] values for one pct, e.g. for 0pct without own inputs
        self.pct_overrides = s.get("pct", {})
        for pct, override in self.pct_overrides.items():
            if unknown := set(override) - {"config", "run_env"}:
                sys.exit(f"{path}: [pct.{pct}] has unknown keys {sorted(unknown)}, use config and run_env.")

    def apply_experiment(self, exp: dict):
        """config (a pattern like config_pattern) and [run_env] of the experiment definition replace config_pattern and
        single [run_env] values of the settings. [pct.<n>] of the settings still applies on top."""
        if "config" in exp:
            if not isinstance(exp["config"], str):
                sys.exit(f"config must be a string (pattern with {{version}} and {{pct}}), got {exp['config']!r}")
            self.config_pattern = exp["config"]
        if "run_env" in exp:
            if not isinstance(exp["run_env"], dict):
                sys.exit(f"run_env must be a table, got {exp['run_env']!r}")
            self.run_env = {**self.run_env, **exp["run_env"]}

    def config(self, pct: int) -> Path:
        pattern = self.pct_overrides.get(str(pct), {}).get("config", self.config_pattern)
        return resolve(pattern.format(version=self.version, pct=pct))

    def extra_env(self, pct: int) -> dict:
        """Variables from [run_env] and [pct.<pct>.run_env] with {version} and {pct} replaced. Values starting with
        '.', '/' or '~' are paths; a glob pattern like matsim-berlin-*.jar becomes its newest match."""
        env = {}
        run_env = {**self.run_env, **self.pct_overrides.get(str(pct), {}).get("run_env", {})}
        for key, value in run_env.items():
            value = str(value).format(version=self.version, pct=pct)
            env[key] = newest(resolve(value)) if value.startswith((".", "/", "~")) else value
        return env

    def network(self, run: Run) -> Path:
        return self.partitions_root / self.network_pattern.format(
            version=self.version, method=run.method, parts=run.parts)


def resolve(path: str) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else (REPO / p).resolve()


def newest(path: Path) -> Path:
    """For a glob pattern like matsim-berlin-*.jar the most recently modified match."""
    if not any(c in path.name for c in "*?["):
        return path
    matches = sorted(path.parent.glob(path.name), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else path


def as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def grid_values(value) -> list:
    """A single value, a list or an inclusive range like { from = 1, to = 64, step = 1 }."""
    if isinstance(value, dict):
        return list(range(int(value["from"]), int(value["to"]) + 1, int(value.get("step", 1))))
    return as_list(value)


def expand_runs(exp: dict) -> list[Run]:
    grids = exp.get("grid")
    if not grids:
        sys.exit("Experiment has no [[grid]] block.")
    runs = {}
    for i, grid in enumerate(grids):
        unknown = set(grid) - set(GRID_KEYS) - {"repetitions"}
        missing = set(GRID_KEYS) - set(grid) - set(GRID_DEFAULTS)
        if unknown or missing:
            sys.exit(f"[[grid]] block {i + 1}: unknown keys {sorted(unknown)}, missing keys {sorted(missing)}")
        repetitions = int(grid.get("repetitions", exp.get("repetitions", 1)))
        values = (grid_values(grid[k]) if k in grid else GRID_DEFAULTS[k] for k in GRID_KEYS)
        for combination in itertools.product(*values):
            v = dict(zip(GRID_KEYS, combination))
            if int(v["parts"]) < 1:
                sys.exit(f"[[grid]] block {i + 1}: parts must be at least 1, got {v['parts']}")
            options = {key: grid_option(key, v[key], i) for key in OPTIONAL_KEYS}
            for rep in range(1, repetitions + 1):
                run = Run(int(v["pct"]), int(v["parts"]), str(v["method"]), bool(v["scoring"]), bool(v["events"]),
                          bool(v["global_sync"]), rep, **options)
                runs[run.run_id] = run
    return sorted(runs.values(), key=Run.sort_key)


def grid_option(key: str, value, block: int):
    """Value of an optional grid key: None (not set), traffic and link in MATSim's spelling, seed as int."""
    if value is None:
        return None
    if key == "seed":
        if isinstance(value, bool) or not isinstance(value, int):
            sys.exit(f"[[grid]] block {block + 1}: seed must be an integer, got {value!r}")
        return value
    names = SHORT_NAMES[key]
    for name, short in names.items():
        if str(value).lower() in (name.lower(), short):
            return name
    sys.exit(f"[[grid]] block {block + 1}: {key} must be one of {list(names)}, got {value!r}")


def time_limit(exp: dict, settings: Settings, run: Run) -> str:
    spec = exp.get("time_limit", {}).get(str(run.pct))
    if spec is None:
        return settings.slurm.get("default_time", "01:00:00")
    if isinstance(spec, str):
        return spec
    for max_parts, limit in sorted(spec):
        if run.parts <= max_parts:
            return limit
    sys.exit(f"time_limit for {run.pct}pct has no entry for {run.parts} parts.")


def iterations(exp: dict) -> int | None:
    """Number of iterations of every run, None keeps the default of the binary."""
    value = exp.get("iterations")
    if value is not None and (not isinstance(value, int) or value < 1):
        sys.exit(f"iterations must be a positive integer, got {value!r}")
    return value


def comment(exp: dict) -> str | None:
    """Free-text description of the experiment, written to description.md."""
    value = exp.get("comment")
    if value is not None and not isinstance(value, str):
        sys.exit(f"comment must be a string, got {value!r}")
    return value.strip() if value and value.strip() else None


def extra_args(exp: dict) -> list[str]:
    """Arguments appended to the command of every run (after those of run-sim.sh and global_sync)."""
    value = exp.get("extra_args", [])
    if not isinstance(value, list) or not all(isinstance(a, str) for a in value):
        sys.exit(f"extra_args must be a list of strings, got {value!r}")
    return value


def apply_filters(runs: list[Run], filters: list[str]) -> list[Run]:
    for f in filters:
        key, _, values = f.partition("=")
        if key not in GRID_KEYS + ("rep",):
            sys.exit(f"--only: unknown key {key!r}, use one of {GRID_KEYS + ('rep',)}")
        allowed = {normalize(v) for v in values.split(",")}
        runs = [r for r in runs if filter_names(r, key) & allowed]
    return runs


def filter_names(run: Run, key: str) -> set[str]:
    """The value of a run for --only, for traffic and link also the short form of the run id."""
    value = getattr(run, key)
    names = {normalize(value)}
    if key in SHORT_NAMES and value is not None:
        names.add(SHORT_NAMES[key][value])
    return names


def normalize(value) -> str:
    s = str(value).lower()
    return {"true": "on", "false": "off"}.get(s, s)


# ----------------------------------------------------------------------
# Experiment directory: manifest, binary snapshots, build info
# ----------------------------------------------------------------------

def read_manifest(exp_dir: Path) -> dict[str, str]:
    """Returns the latest job id per run id."""
    path = exp_dir / "manifest.csv"
    if not path.exists():
        return {}
    with open(path, newline="") as f:
        return {row["run_id"]: row["job_id"] for row in csv.DictReader(f)}


def append_manifest(exp_dir: Path, run_id: str, job_id: str):
    path = exp_dir / "manifest.csv"
    new = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({"run_id": run_id, "job_id": job_id, "submitted_at": now()})


def read_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Snapshot:
    source: Path
    target: Path    # <root>/<sha12>/<name of source>
    digest: str


def plan_snapshot(source: Path, root: Path, update: bool, what: str) -> Snapshot:
    """Where source is copied to in <root>/<sha12>/. Exits if other snapshots exist and update is not set."""
    digest = sha256(source)
    snapshot_dir = root / digest[:12]
    if not snapshot_dir.exists():
        existing = sorted(p.name for p in root.glob("*") if p.is_dir())
        if existing and not update:
            sys.exit(f"The {what} changed since the last submission of this experiment (snapshots: {existing}).\n"
                     f"Use --update-binary to submit the remaining runs with the new {what}.")
    return Snapshot(source, snapshot_dir / source.name, digest)


def copy_snapshot(snapshot: Snapshot) -> bool:
    """Copies the file unless it is there already. Returns whether it was copied."""
    if snapshot.target.exists():
        return False
    snapshot.target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snapshot.source, snapshot.target)
    return True


def plan_env_snapshots(settings: Settings, exp_dir: Path, runs: list[Run], update: bool) -> dict[Path, Snapshot]:
    """Snapshots of the files of the SNAPSHOT_ENV variables of these runs, by source path."""
    sources = {(key, value) for pct in {r.pct for r in runs} for key, value in settings.extra_env(pct).items()
               if key in SNAPSHOT_ENV and isinstance(value, Path)}
    return {source: plan_snapshot(source, exp_dir / SNAPSHOT_ENV[key], update, key) for key, source in sorted(sources)}


def write_build_info(exp_dir: Path, settings: Settings, digest: str):
    path = exp_dir / "build_info.json"
    info = read_json(path) or {}
    info[digest] = {
        "snapshot_at": now(),
        "binary": str(settings.binary),
        "binary_mtime": datetime.datetime.fromtimestamp(settings.binary.stat().st_mtime).isoformat(),
        "repos": {str(REPO): git_info(REPO), **library_info()},
    }
    path.write_text(json.dumps(info, indent=2) + "\n")


def library_info() -> dict:
    """git info of the simulation library matsim-rust: of its checkout for a path dependency in Cargo.toml, otherwise
    the commit that Cargo.lock pins for the git dependency."""
    rust = REPO / "src/main/rust"
    dependency = re.search(r'^matsim-rust\s*=\s*\{([^}]*)\}', (rust / "Cargo.toml").read_text(), re.MULTILINE)
    path = re.search(r'path\s*=\s*"([^"]+)"', dependency.group(1)) if dependency else None
    if path:
        repo = (rust / path.group(1)).resolve()
        return {str(repo): git_info(repo)}
    lock = re.search(r'name = "matsim-rust"\nversion = "[^"]*"\nsource = "git\+([^#"]+)#([0-9a-f]+)"',
                     (rust / "Cargo.lock").read_text())
    return {lock.group(1): {"commit": lock.group(2), "branch": None, "dirty": False}} if lock else {}


def git_info(path: Path) -> dict:
    def git(*args):
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    status = git("status", "--porcelain", "--untracked-files=no")
    return {"commit": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(status) if status is not None else None}


def write_description(exp_dir: Path, name: str, text: str, settings_file: Path, definition: str, num_runs: int,
                      iters: int | None):
    """description.md: the comment of the experiment and the binaries of build_info.json. Rewritten at every
    submission, earlier comments remain in the copies experiment.<timestamp>.toml."""
    lines = [f"# {name}", "", text, "", "---", "",
             f"Written by `cluster.py submit` on {now()} with settings `{repo_relative(settings_file)}` and definition "
             f"`{definition}` ({num_runs} runs, {iters or 'default'} iterations).",
             "", "Binaries (`build_info.json`):", ""]
    for digest, info in (read_json(exp_dir / "build_info.json") or {}).items():
        repos = ", ".join(f"{repo_name(repo)} {(git.get('commit') or '?')[:7]}{' (dirty)' if git.get('dirty') else ''}"
                          for repo, git in info.get("repos", {}).items())
        lines.append(f"- `{digest[:12]}` {Path(info['binary']).name}, snapshot {info['snapshot_at']}: {repos}")
    for key, directory in SNAPSHOT_ENV.items():
        snapshots = sorted((exp_dir / directory).glob("*/*"), key=lambda p: p.stat().st_mtime)
        if snapshots:
            lines += ["", f"`{key}` (`{directory}/`):", ""]
            lines += [f"- `{p.parent.name}` {p.name}, modified "
                      f"{datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds')}"
                      for p in snapshots]
    (exp_dir / DESCRIPTION_FILE).write_text("\n".join(lines) + "\n")


def repo_name(repo: str) -> str:
    """Last component of a checkout path or git URL, e.g. matsim-rust."""
    return PurePosixPath(repo.split("?")[0].rstrip("/")).name.removesuffix(".git")


def repo_relative(path: Path) -> str:
    path = Path(path).resolve()
    return str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)


# ----------------------------------------------------------------------
# submit
# ----------------------------------------------------------------------

def submit(args):
    settings = Settings(args.settings)
    exp_file = Path(args.experiment).resolve()
    with open(exp_file, "rb") as f:
        exp = tomllib.load(f)
    if unknown := set(exp) - EXPERIMENT_KEYS:
        sys.exit(f"{exp_file}: unknown keys {sorted(unknown)}, use {sorted(EXPERIMENT_KEYS)}.")
    settings.apply_experiment(exp)
    name = exp.get("name", exp_file.stem)
    exp_dir = settings.out_root / name
    all_runs = expand_runs(exp)
    runs = apply_filters(all_runs, args.only)
    iters = iterations(exp)
    text = comment(exp)
    args_extra = extra_args(exp)

    # check inputs
    problems = [f"binary {settings.binary} does not exist"] if not settings.binary.exists() else []
    problems += [f"config {settings.config(pct)} does not exist"
                 for pct in sorted({r.pct for r in runs}) if not settings.config(pct).exists()]
    missing_networks = sorted({str(settings.network(r)) for r in runs if not settings.network(r).exists()})
    problems += [f"network {n} does not exist" for n in missing_networks]
    problems += [f"{key} {path} does not exist" for key, path in sorted(
        {(k, v) for pct in {r.pct for r in runs} for k, v in settings.extra_env(pct).items()
         if isinstance(v, Path) and not v.exists()})]
    if settings.run_env.get("ENGINE") == "dsim" and any(r.global_sync for r in runs):
        problems.append("global_sync = true is only supported by rust")
    if problems:
        print(f"{len(problems)} problem(s):", *problems, sep="\n  ", file=sys.stderr)
        if missing_networks:
            print("Create missing networks locally with scripts/partition-networks.sh and copy them to "
                  f"{settings.partitions_root}.", file=sys.stderr)
        if not args.dry_run:
            sys.exit(1)

    manifest = read_manifest(exp_dir)
    todo = [run for run in runs if run.run_id not in manifest]

    print(f"Experiment {name}: {len(runs)} runs, {len(runs) - len(todo)} already submitted, "
          f"{len(todo)} to submit, {iters or 'default'} iterations -> {exp_dir}")
    if text:
        print(f"Comment (-> {DESCRIPTION_FILE}):\n" + textwrap.indent(text, "  | ", lambda line: True))
    else:
        print(f"No comment in the definition, {DESCRIPTION_FILE} is not written.")
    width = max([48] + [len(run.run_id) for run in todo])
    for run in todo:
        print(f"  {run.run_id:<{width}} {time_limit(exp, settings, run)}")
    if args.dry_run:
        if todo:
            print("\nExample command:\n  " + shlex.join(sbatch_command(settings, name, exp_dir, todo[0],
                                                                       time_limit(exp, settings, todo[0]))))
            env, _ = run_env(settings, todo[0], Snapshot(settings.binary, settings.binary, ""), {}, iters, args_extra)
            print(f"\nrun.env of {todo[0].run_id} (with the original files, which submit copies into the "
                  f"experiment):\n" + textwrap.indent(env, "  "), end="")
        print("\nDry run, nothing submitted.")
        return
    if not todo:
        return

    # check all snapshots before copying any of them
    binary = plan_snapshot(settings.binary, exp_dir / "bin", args.update_binary, "binary")
    env_snapshots = plan_env_snapshots(settings, exp_dir, todo, args.update_binary)
    exp_dir.mkdir(parents=True, exist_ok=True)
    if copy_snapshot(binary):
        write_build_info(exp_dir, settings, binary.digest)
    for snapshot in env_snapshots.values():
        copy_snapshot(snapshot)
    definition = f"experiment.{datetime.datetime.now():%Y%m%d-%H%M%S}.toml"
    shutil.copy2(exp_file, exp_dir / definition)
    if text:
        write_description(exp_dir, name, text, args.settings, definition, len(all_runs), iters)

    for run in todo:
        run_dir = exp_dir / "runs" / run.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "result.json").unlink(missing_ok=True)
        limit = time_limit(exp, settings, run)
        write_run_files(settings, name, run, run_dir, binary, env_snapshots, limit, iters, args_extra)
        result = subprocess.run(sbatch_command(settings, name, exp_dir, run, limit),
                                capture_output=True, text=True)
        if result.returncode != 0:
            sys.exit(f"sbatch failed for {run.run_id}: {result.stderr.strip()}")
        job_id = result.stdout.strip().split(";")[0]
        append_manifest(exp_dir, run.run_id, job_id)
        print(f"Submitted {run.run_id} as job {job_id}")


def run_env(settings: Settings, run: Run, binary: Snapshot, env_snapshots: dict[Path, Snapshot],
            iters: int | None, args_extra: list[str]) -> tuple[str, dict]:
    """Content of run.env and the variables in it (without EXTRA_ARGS)."""
    env = {
        "BIN": binary.target,
        "CONFIG": settings.config(run.pct),
        "NUM_PARTS": run.parts,
        "NETWORK": settings.network(run),
        "SCORING_MODE": "enabled" if run.scoring else "disabled",
        "WRITE_EVENTS": "file" if run.events else "none",
    }
    for key, variable in (("traffic", "TRAFFIC_DYNAMICS"), ("link", "LINK_DYNAMICS"), ("seed", "SEED")):
        if getattr(run, key) is not None:
            env[variable] = getattr(run, key)
    for key, value in settings.extra_env(run.pct).items():
        env[key] = env_snapshots[value].target if key in SNAPSHOT_ENV and value in env_snapshots else value
    if iters is not None:
        env["LAST_ITERATION"] = iters - 1
    lines = [f"{k}={shlex.quote(str(v))}\n" for k, v in env.items()]
    # global_sync: barrier of all partitions in every time step, the configs have global_sync: false
    extra = (["--set", "computational_setup.global_sync=true"] if run.global_sync else []) + args_extra
    if extra:
        lines.append(f"EXTRA_ARGS=({' '.join(shlex.quote(a) for a in extra)})\n")
    return "".join(lines), env


def write_run_files(settings: Settings, name: str, run: Run, run_dir: Path, binary: Snapshot,
                    env_snapshots: dict[Path, Snapshot], limit: str, iters: int | None, args_extra: list[str]):
    text, env = run_env(settings, run, binary, env_snapshots, iters, args_extra)
    (run_dir / "run.env").write_text(text)
    params = {"experiment": name, "run_id": run.run_id, **run.params(), "iterations": iters,
              "scenario_version": settings.version, "time_limit": limit, "config": str(env["CONFIG"]),
              "network": str(env["NETWORK"]), "binary": str(binary.target), "binary_sha256": binary.digest}
    if args_extra:
        params["extra_args"] = args_extra
    by_target = {snapshot.target: snapshot for snapshot in env_snapshots.values()}
    for key in SNAPSHOT_ENV:
        if (snapshot := by_target.get(env.get(key))) is not None:
            params |= {key.lower(): str(snapshot.target), f"{key.lower()}_sha256": snapshot.digest}
    params["submitted_at"] = now()
    (run_dir / "params.json").write_text(json.dumps(params, indent=2) + "\n")


def sbatch_command(settings: Settings, name: str, exp_dir: Path, run: Run, limit: str) -> list[str]:
    run_dir = exp_dir / "runs" / run.run_id
    cmd = ["sbatch", "--parsable", f"--job-name={name}", f"--comment={run.run_id}", f"--time={limit}",
           f"--output={run_dir}/slurm-%j.log"]
    if "partition" in settings.slurm:
        cmd.append(f"--partition={settings.slurm['partition']}")
    if settings.slurm.get("mail_user"):
        cmd += [f"--mail-user={settings.slurm['mail_user']}", f"--mail-type={settings.slurm.get('mail_type', 'FAIL')}"]
    return cmd + [str(RUN_SCRIPT), str(run_dir)]


# ----------------------------------------------------------------------
# collect
# ----------------------------------------------------------------------

def collect(args):
    settings = Settings(args.settings)
    exp_dir = Path(args.experiment)
    if not exp_dir.is_dir():
        exp_dir = settings.out_root / args.experiment
    if not (exp_dir / "runs").is_dir():
        sys.exit(f"{exp_dir} is not an experiment directory.")

    manifest = read_manifest(exp_dir)
    accounting = sacct(list(manifest.values()))
    run_dirs = sorted(p for p in (exp_dir / "runs").iterdir() if p.is_dir())
    all_params = {d: read_json(d / "params.json") or {"run_id": d.name} for d in run_dirs}
    all_results = {d: read_json(d / "result.json") or {} for d in run_dirs}
    # columns of optional grid keys and of the simulation time (only runs with TRIPS_JAR) only if a run has them, so
    # runs.csv of older experiments stays the same
    keys = [k for k in GRID_KEYS if k not in OPTIONAL_KEYS or any(k in p for p in all_params.values())]
    sim_keys = [k for k in ("sim_elapsed_s", "sim_end") if any(k in r for r in all_results.values())]
    rows = []
    for run_dir in run_dirs:
        params = all_params[run_dir]
        result = all_results[run_dir]
        job_id = manifest.get(run_dir.name, "")
        acc = accounting.get(job_id, {})
        rows.append({
            **{k: params.get(k, GRID_DEFAULTS.get(k, [None])[0])
               for k in ("run_id", *keys, "rep", "iterations", "time_limit", "binary_sha256")},
            "job_id": job_id,
            "slurm_state": acc.get("state", ""),
            "slurm_elapsed": acc.get("elapsed", ""),
            "max_rss_mb": acc.get("max_rss_mb", ""),
            "node": result.get("node", acc.get("node", "")),
            "exit_code": result.get("exit_code", ""),
            "elapsed_s": result.get("elapsed_s", ""),
            **{k: result.get(k, "") for k in sim_keys},
            "start": result.get("start", ""),
            "end": result.get("end", ""),
            "run_dir": str(run_dir.relative_to(exp_dir)),
        })

    out = exp_dir / "runs.csv"
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["run_id"])
        writer.writeheader()
        writer.writerows(rows)

    states = {}
    for row in rows:
        state = row["slurm_state"] or ("COMPLETED" if row["exit_code"] == 0 else "UNKNOWN")
        states[state] = states.get(state, 0) + 1
    print(f"{len(rows)} runs: " + ", ".join(f"{k} {v}" for k, v in sorted(states.items())))
    print(f"Written {out}")


def sacct(job_ids: list[str]) -> dict[str, dict]:
    """State, elapsed time and node from the job allocation, peak memory as maximum over its steps."""
    if not job_ids or shutil.which("sacct") is None:
        return {}
    result = {}
    for i in range(0, len(job_ids), 500):
        out = subprocess.run(["sacct", "-j", ",".join(job_ids[i:i + 500]), "--noheader", "--parsable2",
                              "--format=JobID,State,Elapsed,MaxRSS,NodeList"],
                             capture_output=True, text=True, check=True).stdout
        for line in out.splitlines():
            job_step, state, elapsed, max_rss, node = line.split("|")
            job_id = job_step.split(".")[0]
            entry = result.setdefault(job_id, {})
            if job_step == job_id:
                entry.update(state=state.split()[0], elapsed=elapsed, node=node)
            if max_rss:
                entry["max_rss_mb"] = max(entry.get("max_rss_mb", 0), rss_to_mb(max_rss))
    return result


def rss_to_mb(value: str) -> int:
    units = {"K": 1 / 1024, "M": 1, "G": 1024, "T": 1024 * 1024}
    if value[-1] in units:
        return round(float(value[:-1]) * units[value[-1]])
    return round(float(value) / 1024 / 1024)


# ----------------------------------------------------------------------
# fetch (runs locally)
# ----------------------------------------------------------------------

def fetch(args):
    settings = Settings(args.settings)
    if not {"host", "remote_repo", "target"} <= set(settings.fetch):
        sys.exit(f"{args.settings} needs host, remote_repo and target in [fetch].")
    host = settings.fetch["host"]
    remote_repo = settings.fetch["remote_repo"].removeprefix("~/")
    experiment = args.experiment.rstrip("/")
    name = experiment_name(experiment, settings.out_root_setting)
    remote_dir = remote_path(experiment if "/" in experiment else f"{settings.out_root_setting}/{experiment}",
                             remote_repo)
    target = resolve(settings.fetch["target"])
    local_dir = target / name

    if not args.dry_run and not args.no_collect:
        settings_file = Path(args.settings).resolve().relative_to(REPO)
        ssh(host, f"cd {shlex.quote(remote_repo)} && uv run scripts/cluster/cluster.py "
                  f"--settings {shlex.quote(str(settings_file))} collect {shlex.quote(experiment)}")

    files = remote_files(host, remote_dir)
    patterns = FETCH_FILES + settings.fetch.get("extra_files", [])
    selected = {}
    per_pattern = {p: [0, 0] for p in patterns}
    for path, size in files.items():
        pattern = next((p for p in patterns if PurePosixPath(path).full_match(p)), None)
        if pattern:
            selected[path] = size
            per_pattern[pattern][0] += 1
            per_pattern[pattern][1] += size

    print(f"{host}:{remote_dir} -> {local_dir}")
    for pattern, (count, size) in per_pattern.items():
        if count:
            print(f"  {count:6d} files {size / 1e6:10.1f} MB  {pattern}")
    print(f"{len(selected)} of {len(files)} files, {sum(selected.values()) / 1e6:.1f} MB "
          f"(not copied: {(sum(files.values()) - sum(selected.values())) / 1e9:.1f} GB)")
    if args.dry_run:
        print("Dry run, nothing copied.")
        return
    if not selected:
        sys.exit("Nothing to copy.")

    local_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as file_list:
        file_list.write("".join(f"{path}\n" for path in sorted(selected)))
        file_list.flush()
        subprocess.run(["rsync", "-a", "--partial", f"--files-from={file_list.name}",
                        f"{host}:{remote_dir}/", f"{local_dir}/"], check=True)
    relative_run_dirs(local_dir / "runs.csv")
    svn_add(target, local_dir, sorted(selected))


def experiment_name(experiment: str, out_root: str) -> str:
    """Local directory name: the path below out_root (e.g. archive/scaling), otherwise the last component."""
    path = PurePosixPath(experiment)
    if path.is_relative_to(out_root):
        return str(path.relative_to(out_root))
    return path.name


def remote_path(path: str, remote_repo: str) -> str:
    """A path on the cluster for ssh and rsync: absolute or relative to the home directory."""
    if path.startswith("~/"):
        return path[2:]
    return path if path.startswith("/") else f"{remote_repo}/{path}"


def ssh(host: str, command: str):
    if subprocess.run(["ssh", host, command]).returncode != 0:
        sys.exit(f"Failed on {host}: {command}")


def remote_files(host: str, remote_dir: str) -> dict[str, int]:
    """All files below remote_dir with their size."""
    result = subprocess.run(["ssh", host, f"cd {shlex.quote(remote_dir)} && find . -type f -printf '%P\\t%s\\n'"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"Could not list {host}:{remote_dir}: {result.stderr.strip()}")
    files = {}
    for line in result.stdout.splitlines():
        path, size = line.rsplit("\t", 1)
        files[path] = int(size)
    return files


def relative_run_dirs(runs_csv: Path):
    """runs.csv written by older versions of collect has absolute run directories on the cluster."""
    if not runs_csv.exists():
        return
    with open(runs_csv, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows or "run_dir" not in reader.fieldnames:
        return
    for row in rows:
        row["run_dir"] = f"runs/{row['run_id']}"
    with open(runs_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def svn_add(target: Path, local_dir: Path, files: list[str]):
    """Schedules the copied files for addition if target is in an svn working copy. Nothing is committed."""
    if shutil.which("svn") is None or subprocess.run(["svn", "info", str(target.parent)],
                                                     capture_output=True).returncode != 0:
        print(f"{target} is not in an svn working copy, nothing added.")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as targets:
        targets.write("".join(f"{local_dir / path}\n" for path in files))
        targets.flush()
        subprocess.run(["svn", "add", "--force", "--parents", "--targets", targets.name],
                       stdout=subprocess.DEVNULL, check=True)
    status = subprocess.run(["svn", "status", "-q", str(local_dir)], capture_output=True, text=True, check=True)
    changes = Counter(line[0] for line in status.stdout.splitlines())
    print(f"svn: {changes['A']} added, {changes['M']} modified. Not committed, check and commit with\n"
          f"  svn status -q {local_dir}\n  svn commit -m '...' {target}")


# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--settings", type=Path, default=SCRIPT_DIR / "cluster.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("submit", help="submit all runs of an experiment that were not submitted yet")
    p.add_argument("experiment", help="experiment definition, e.g. experiments/example.toml")
    p.add_argument("--dry-run", "--dry", action="store_true", help="only print what would be submitted")
    p.add_argument("--only", action="append", default=[], metavar="KEY=V1,V2",
                   help="only runs with these values, e.g. pct=1 or parts=16,32 or scoring=off (repeatable)")
    p.add_argument("--update-binary", action="store_true",
                   help="allow submitting with a binary that differs from earlier submissions")
    p.set_defaults(func=submit)

    p = sub.add_parser("collect", help="write runs.csv with parameters, Slurm accounting and results")
    p.add_argument("experiment", help="experiment name or directory")
    p.set_defaults(func=collect)

    p = sub.add_parser("fetch", help="run locally: collect on the cluster, then copy the results into runs-svn")
    p.add_argument("experiment", help="experiment name, or a directory relative to the repository on the cluster")
    p.add_argument("--dry-run", "--dry", action="store_true", help="only list the files that would be copied")
    p.add_argument("--no-collect", action="store_true", help="do not run collect on the cluster first")
    p.set_defaults(func=fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
