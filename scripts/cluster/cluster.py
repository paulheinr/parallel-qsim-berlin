#!/usr/bin/env python3
"""Submit profiling experiments of berlin_iterations_v7 to Slurm and collect their results.

    uv run scripts/cluster/cluster.py submit experiments/example.toml --dry-run
    uv run scripts/cluster/cluster.py submit experiments/example.toml --only pct=1
    uv run scripts/cluster/cluster.py collect example

Paths and Slurm settings are read from scripts/cluster/cluster.toml. See scripts/cluster/README.md.
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
import tomllib
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[1]
RUN_SCRIPT = SCRIPT_DIR / "run-sim.sh"
GRID_KEYS = ("pct", "parts", "method", "scoring", "events")
MANIFEST_FIELDS = ["run_id", "job_id", "submitted_at"]


@dataclass(frozen=True)
class Run:
    pct: int
    parts: int
    method: str
    scoring: bool
    events: bool
    rep: int

    @property
    def run_id(self) -> str:
        return (f"{self.pct}pct_{self.method}_p{self.parts:03d}"
                f"_score-{on_off(self.scoring)}_events-{on_off(self.events)}_r{self.rep}")

    def params(self) -> dict:
        return {"pct": self.pct, "parts": self.parts, "method": self.method,
                "scoring": self.scoring, "events": self.events, "rep": self.rep}


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
        self.out_root = resolve(s["out_root"])
        self.partitions_root = resolve(s["partitions_root"])
        self.version = s["scenario_version"]
        self.config_pattern = s["config_pattern"]
        self.network_pattern = s["network_pattern"]
        self.binary = resolve(s["binary"])
        self.slurm = s.get("slurm", {})

    def config(self, pct: int) -> Path:
        return resolve(self.config_pattern.format(version=self.version, pct=pct))

    def network(self, run: Run) -> Path:
        return self.partitions_root / self.network_pattern.format(
            version=self.version, method=run.method, parts=run.parts)


def resolve(path: str) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else (REPO / p).resolve()


def as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def expand_runs(exp: dict) -> list[Run]:
    grids = exp.get("grid")
    if not grids:
        sys.exit("Experiment has no [[grid]] block.")
    runs = {}
    for i, grid in enumerate(grids):
        unknown = set(grid) - set(GRID_KEYS) - {"repetitions"}
        missing = set(GRID_KEYS) - set(grid)
        if unknown or missing:
            sys.exit(f"[[grid]] block {i + 1}: unknown keys {sorted(unknown)}, missing keys {sorted(missing)}")
        repetitions = int(grid.get("repetitions", exp.get("repetitions", 1)))
        for pct, parts, method, scoring, events in itertools.product(*(as_list(grid[k]) for k in GRID_KEYS)):
            if int(parts) < 1:
                sys.exit(f"[[grid]] block {i + 1}: parts must be at least 1, got {parts}")
            for rep in range(1, repetitions + 1):
                run = Run(int(pct), int(parts), str(method), bool(scoring), bool(events), rep)
                runs[run.run_id] = run
    return sorted(runs.values(), key=lambda r: (r.pct, r.method, r.parts, not r.scoring, r.events, r.rep))


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


def apply_filters(runs: list[Run], filters: list[str]) -> list[Run]:
    for f in filters:
        key, _, values = f.partition("=")
        if key not in GRID_KEYS + ("rep",):
            sys.exit(f"--only: unknown key {key!r}, use one of {GRID_KEYS + ('rep',)}")
        allowed = {normalize(v) for v in values.split(",")}
        runs = [r for r in runs if normalize(getattr(r, key)) in allowed]
    return runs


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


def snapshot_binary(settings: Settings, exp_dir: Path, update: bool) -> tuple[Path, str]:
    """Copies the binary to <exp>/bin/<sha12>/, so rebuilding does not change queued jobs."""
    digest = sha256(settings.binary)
    snapshot_dir = exp_dir / "bin" / digest[:12]
    target = snapshot_dir / settings.binary.name
    if not snapshot_dir.exists():
        existing = sorted(p.name for p in (exp_dir / "bin").glob("*") if p.is_dir())
        if existing and not update:
            sys.exit(f"The binary changed since the last submission of this experiment (snapshots: {existing}).\n"
                     f"Use --update-binary to submit the remaining runs with the new binary.")
    if not target.exists():
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings.binary, target)
        write_build_info(exp_dir, settings, digest)
    return target, digest


def write_build_info(exp_dir: Path, settings: Settings, digest: str):
    path = exp_dir / "build_info.json"
    info = read_json(path) or {}
    info[digest] = {
        "snapshot_at": now(),
        "binary": str(settings.binary),
        "binary_mtime": datetime.datetime.fromtimestamp(settings.binary.stat().st_mtime).isoformat(),
        "repos": {str(repo): git_info(repo) for repo in (REPO, library_repo())},
    }
    path.write_text(json.dumps(info, indent=2) + "\n")


def library_repo() -> Path:
    """The simulation library as referenced in the Cargo.toml of this repository."""
    cargo = REPO / "src/main/rust/Cargo.toml"
    match = re.search(r'^rust_qsim\s*=\s*\{[^}]*path\s*=\s*"([^"]+)"', cargo.read_text(), re.MULTILINE)
    return (cargo.parent / match.group(1)).resolve() if match else REPO


def git_info(path: Path) -> dict:
    def git(*args):
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    status = git("status", "--porcelain", "--untracked-files=no")
    return {"commit": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(status) if status is not None else None}


# ----------------------------------------------------------------------
# submit
# ----------------------------------------------------------------------

def submit(args):
    settings = Settings(args.settings)
    exp_file = Path(args.experiment).resolve()
    with open(exp_file, "rb") as f:
        exp = tomllib.load(f)
    name = exp.get("name", exp_file.stem)
    exp_dir = settings.out_root / name
    runs = apply_filters(expand_runs(exp), args.only)

    # check inputs
    problems = [f"binary {settings.binary} does not exist"] if not settings.binary.exists() else []
    problems += [f"config {settings.config(pct)} does not exist"
                 for pct in sorted({r.pct for r in runs}) if not settings.config(pct).exists()]
    missing_networks = sorted({str(settings.network(r)) for r in runs if not settings.network(r).exists()})
    problems += [f"network {n} does not exist" for n in missing_networks]
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
          f"{len(todo)} to submit -> {exp_dir}")
    for run in todo:
        print(f"  {run.run_id:<48} {time_limit(exp, settings, run)}")
    if args.dry_run:
        if todo:
            print("\nExample command:\n  " + shlex.join(sbatch_command(settings, name, exp_dir, todo[0],
                                                                       time_limit(exp, settings, todo[0]))))
        print("\nDry run, nothing submitted.")
        return
    if not todo:
        return

    exp_dir.mkdir(parents=True, exist_ok=True)
    binary, digest = snapshot_binary(settings, exp_dir, args.update_binary)
    shutil.copy2(exp_file, exp_dir / f"experiment.{datetime.datetime.now():%Y%m%d-%H%M%S}.toml")

    for run in todo:
        run_dir = exp_dir / "runs" / run.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "result.json").unlink(missing_ok=True)
        limit = time_limit(exp, settings, run)
        write_run_files(settings, name, run, run_dir, binary, digest, limit)
        result = subprocess.run(sbatch_command(settings, name, exp_dir, run, limit),
                                capture_output=True, text=True)
        if result.returncode != 0:
            sys.exit(f"sbatch failed for {run.run_id}: {result.stderr.strip()}")
        job_id = result.stdout.strip().split(";")[0]
        append_manifest(exp_dir, run.run_id, job_id)
        print(f"Submitted {run.run_id} as job {job_id}")


def write_run_files(settings: Settings, name: str, run: Run, run_dir: Path, binary: Path, digest: str,
                    limit: str):
    env = {
        "BIN": binary,
        "CONFIG": settings.config(run.pct),
        "NUM_PARTS": run.parts,
        "NETWORK": settings.network(run),
        "SCORING_MODE": "enabled" if run.scoring else "disabled",
        "WRITE_EVENTS": "file" if run.events else "none",
    }
    (run_dir / "run.env").write_text("".join(f"{k}={shlex.quote(str(v))}\n" for k, v in env.items()))
    params = {"experiment": name, "run_id": run.run_id, **run.params(), "scenario_version": settings.version,
              "time_limit": limit, "config": str(env["CONFIG"]), "network": str(env["NETWORK"]),
              "binary": str(binary), "binary_sha256": digest, "submitted_at": now()}
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
    rows = []
    for run_dir in sorted(p for p in (exp_dir / "runs").iterdir() if p.is_dir()):
        params = read_json(run_dir / "params.json") or {"run_id": run_dir.name}
        result = read_json(run_dir / "result.json") or {}
        job_id = manifest.get(run_dir.name, "")
        acc = accounting.get(job_id, {})
        rows.append({
            **{k: params.get(k) for k in ("run_id", *GRID_KEYS, "rep", "time_limit", "binary_sha256")},
            "job_id": job_id,
            "slurm_state": acc.get("state", ""),
            "slurm_elapsed": acc.get("elapsed", ""),
            "max_rss_mb": acc.get("max_rss_mb", ""),
            "node": result.get("node", acc.get("node", "")),
            "exit_code": result.get("exit_code", ""),
            "elapsed_s": result.get("elapsed_s", ""),
            "start": result.get("start", ""),
            "end": result.get("end", ""),
            "run_dir": str(run_dir),
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
