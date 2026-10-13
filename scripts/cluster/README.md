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
conda activate router                       # Python >= 3.11
cd src/main/rust && cargo build --release && cd -
python scripts/cluster/cluster.py submit experiments/example.toml --dry-run
python scripts/cluster/cluster.py submit experiments/example.toml
```

- Runs that are already in `manifest.csv` are skipped, so submitting again only adds new runs (e.g. after
  increasing `repetitions` or adding values to the grid). To resubmit a run, delete its line from `manifest.csv`.
- `--only pct=1 --only parts=16,32` submits a subset.
- The binary is copied into the experiment directory, so rebuilding does not affect queued jobs. If the build
  changed since the last submission of the experiment, `--update-binary` is required.
- All jobs of an experiment have the experiment name as job name: `squeue --me --name example`,
  `scancel --name example`. The run id is in the job comment.

Paths and Slurm settings are in `scripts/cluster/cluster.toml`.

## 3. Collect results

```bash
python scripts/cluster/cluster.py collect example
```

writes `<out_root>/example/runs.csv` with the parameters, Slurm state, elapsed time and peak memory (`sacct`) and
`result.json` of every run.

## Layout

```
<out_root>/<experiment>/
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
