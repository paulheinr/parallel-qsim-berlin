# Profiling runs on the cluster

A run of `berlin_iterations_v7` is defined by scenario size (`pct`), number of partitions (`parts`), partition
method (`method`), scoring on/off (`scoring`) and event writing on/off (`events`).

## 1. Partition networks (locally)

```bash
scripts/partition-networks.sh metis "1 3 10" 1 192
```

writes `shared-svn/projects/rust-qsim/berlin-v7.1/network/berlin-v7.1-<pct>pct.network.<method>.<NNN>.xml.zst`
(`partitions_root` and `network_pattern` in `cluster.toml` point there).

Partition methods are YAML files in `input/partitioning/` (a serialized `PartitionMethod`). The file stem is the
method label in file names and experiment definitions. A new method is a new file, e.g. `metis-uf1.03.yml`.

## 2. Submit an experiment (on the cluster)

```bash
cd src/main/rust && cargo build --release && cd -
uv run scripts/cluster/cluster.py submit experiments/example.toml --dry-run
uv run scripts/cluster/cluster.py submit experiments/example.toml
```

`uv run` uses the Python version and environment from `pyproject.toml`/`uv.lock` in the repository root and
creates `.venv` on first use (`uv sync` does that explicitly).

- `iterations = 10` at the top level of an experiment sets the number of iterations of all runs (passed as
  `controller.last_iteration=9`). Without it, the binary runs its default of two iterations.
- A grid value can be an inclusive range: `parts = { from = 1, to = 64 }` (optional `step`).
- `comment = """..."""` at the top level is a free-text description (Markdown). Every submission writes it to
  `description.md` in the experiment directory, together with the binaries and commits of `build_info.json`. `fetch`
  copies it into runs-svn. The comments of earlier submissions remain in the copies `experiment.<timestamp>.toml`.

- Runs that are already in `manifest.csv` are skipped, so submitting again only adds new runs (e.g. after
  increasing `repetitions` or adding values to the grid). To resubmit a run, delete its line from `manifest.csv`.
- `--only pct=1 --only parts=16,32` submits a subset.
- The binary is copied into the experiment directory, so rebuilding does not affect queued jobs. If the build
  changed since the last submission of the experiment, `--update-binary` is required.
- All jobs of an experiment have the experiment name as job name: `squeue --me --name example`,
  `scancel --name example`. The run id is in the job comment.

Paths and Slurm settings are in `scripts/cluster/cluster.toml`.

`pct = 0` is an empty population on the same network and partitions, to measure the synchronization without agents.
Rust uses `input/v7.1/berlin-v7.1.0pct.config.yml` (the 1pct inputs without a population path), DSim the 1pct config
with the empty `input/v7.1/berlin-v7.1-0pct.plans.xml`.

### DSim (Java)

The same runs with DSim, branch `ph/v7.1.1-dsim` of matsim-berlin (see `README-dsim-benchmark.md` there), use the
settings `cluster-dsim.toml`. They use the same partitioned networks as rust.

```bash
cd ../matsim-berlin && ./mvnw clean package -DskipTests && cd -
uv run scripts/cluster/cluster.py --settings scripts/cluster/cluster-dsim.toml submit experiments/dsim-scaling.toml --dry-run
uv run scripts/cluster/cluster.py --settings scripts/cluster/cluster-dsim.toml collect dsim-scaling
```

- `binary` may be a glob pattern, the newest match is used (the jar name contains the git commit).
- `[run_env]` is written to `run.env` (`{version}` and `{pct}` are replaced). With `ENGINE = "dsim"`, `run-sim.sh` starts
  the jar. Inputs (`PLANS`, ...) are checked on submission.
- `[pct.<n>]` replaces `config_pattern` (`config = ...`) and single `[run_env]` values (`[pct.<n>.run_env]`) for one
  pct. `cluster-dsim.toml` uses it for 0pct, which has no scenario of its own in public-svn.
- DSim always scores, so `scoring = false` is not supported.
- The stopwatch has a resolution of one second. Phase times in ms per iteration:
  `python3 ../matsim-berlin/src/main/python/dsim_phase_times.py <run_dir>/output/*.logfile.log <run_dir>/phases.csv`

## 3. Collect results

```bash
uv run scripts/cluster/cluster.py collect example
```

writes `<out_root>/example/runs.csv` with the parameters, Slurm state, elapsed time and peak memory (`sacct`) and
`result.json` of every run. `run_dir` is relative to the experiment directory.

## 4. Fetch results into runs-svn (locally)

```bash
uv run scripts/cluster/cluster.py fetch example --dry-run
uv run scripts/cluster/cluster.py fetch example
uv run scripts/cluster/cluster.py --settings scripts/cluster/cluster-dsim.toml fetch dsim-scaling
```

runs `collect` on the cluster, copies the evaluation files (`FETCH_FILES` in `cluster.py`: metadata, `result.json`,
Slurm logs, rust `instrument/`, DSim stats and logs) with rsync into `<target>/<experiment>/` and schedules them for
addition in svn. It does not commit. Binary snapshots, plans, events, `ITERS/` and per-process logs stay on the
cluster. Fetching again only copies new or changed files.

- `[fetch]` in the settings: `host` (ssh alias), `remote_repo` (this repository on the cluster, relative to `~`),
  `target` (local runs-svn directory) and optionally `extra_files` (more patterns, e.g.
  `"runs/*/output/runtimes-*/tasks.csv"`).
- An experiment outside `out_root` is given as a directory relative to the repository on the cluster, e.g.
  `fetch output/experiments/archive/scaling` (stored as `<target>/archive/scaling`).
- `--no-collect` skips `collect`. `run_dir` in `runs.csv` of older versions of `collect` is rewritten to
  `runs/<run_id>`.
- Commit the target directory, e.g. `svn commit -m '...' ~/runs-svn/matsim-rust/iterations-vs-dsim-2026`.

## Layout

```
<out_root>/<experiment>/
    description.md                # comment of the definition, binaries and commits (only with comment)
    experiment.<timestamp>.toml   # copy of the definition at every submission
    build_info.json               # git commit and dirty flag of both repositories per binary
    bin/<sha12>/berlin_iterations_v7
    manifest.csv                  # run_id, job_id, submitted_at
    runs.csv                      # written by collect
    runs/<run_id>/                # e.g. 1pct_metis_p016_score-on_events-off_r1
        params.json  run.env
        slurm-<jobid>.log
        result.json               # job_id, node, start, end, elapsed_s, exit_code
        output/                   # simulation output (instrument/, logs/, ...)
```

`result.json` is written by `run-sim.sh` when the job ends, also on failure, `scancel` and time limit. If it is
missing, the job is pending, running or was killed hard; `collect` also reports the state from `sacct`.

On Lise, `sacct` reports no useful memory usage (MaxRSS of the batch step is 0), so `max_rss_mb` is not meaningful there.

## Running a single run by hand

`run-sim.sh` reads everything from `<run_dir>/run.env` (absolute paths, the script changes into the run directory)
and also works without Slurm: `scripts/cluster/run-sim.sh <run_dir>`.

```bash
BIN=/path/to/src/main/rust/target/release/berlin_iterations_v7
CONFIG=/path/to/input/v7.1/berlin-v7.1.1pct.config.yml
NUM_PARTS=4
NETWORK=/path/to/shared-svn/projects/rust-qsim/berlin-v7.1/network/berlin-v7.1-1pct.network.metis.004.xml.zst
SCORING_MODE=disabled
WRITE_EVENTS=none
EXTRA_ARGS=(--set population.path=/path/to/plans.binpb)      # optional
```
