# Working with the cluster (NHR@ZIB, system "Lise")

Notes for Claude. Facts were checked on 2026-10-15; re-check anything that looks outdated before relying on it.

## Access

- SSH host aliases in `~/.ssh/config`: `hlrn-genoa` (genoa-login.nhr.zib.de, used for this project, partition
  `cpu-genoa`) and `hlrn` (blogin.nhr.zib.de). Remote user `bemheinr`, home `/home/bemheinr`.
- NHR@ZIB requires a passphrase on the key, and I cannot type it. Access works through the user's macOS keychain/agent
  and a shared connection (`ControlMaster auto`, `ControlPersist 8h` for both aliases).
- Always call `ssh -o BatchMode=yes hlrn-genoa '...'` so a missing connection fails instead of hanging. If it fails,
  ask the user to run `ssh hlrn-genoa` once in their terminal. `ssh -O check hlrn-genoa` shows the shared connection.
- Never read, copy or upload private keys. Never store svn or git credentials on the cluster.
- `git push` of this repo over the HTTPS remote fails from my shell (no access to the keychain credentials). Pushing to
  `git@github.com:paulheinr/parallel-qsim-berlin.git` over SSH works (outside the sandbox), then `git fetch origin`.

## Layout

| | cluster | local (Mac) |
|---|---|---|
| this repo | `~/scratch/iterations-rust/parallel-qsim-berlin` | `~/git/parallel-qsim-berlin` |
| simulation library, DSim | `~/scratch/iterations-rust/{matsim-rust,matsim-berlin}` | `~/git/parallel_qsim_rust/matsim_rust`, `~/git/matsim-berlin` |
| svn checkouts | `~/scratch/{shared-svn,public-svn,runs-svn}` | `~/{shared-svn,public-svn,runs-svn}` |
| experiments | `<repo>/output/experiments/<name>/` (`out_root`) | `~/runs-svn/matsim-rust/iterations-vs-dsim-2026/<name>/` |

- Relative paths like `../../shared-svn` in `cluster.toml` / `cluster-dsim.toml` resolve to `~/scratch/...` on the
  cluster and to `~/...` locally, so the same settings work on both.
- The cluster repo has local changes in `src/main/rust/Cargo.toml` and `Cargo.lock`. There, matsim-rust is a git
  dependency (GitHub) and `Cargo.lock` pins its commit (d41dba8 since 2026-10-16). Locally it is a path dependency. Do
  not overwrite these changes. To build a newer matsim-rust from main on the cluster:
  `cargo update -p matsim-rust && cargo build --release` in `src/main/rust` (ask first, see Rules). Cargo is in
  `~/.cargo/env`; the build takes about half a minute.
- To rerun an experiment with a newer library and keep the old runs, give it a new name (a copy of the experiment file,
  e.g. `scaling-v2.toml`). Reusing the name submits nothing, because all runs are already in `manifest.csv`.
- Experiments on the cluster on 2026-10-15: `example`, `scaling` (595 GB), `dsim-scaling` (11 GB) and
  `archive/scaling`. Almost all of the size is plans, events and `ITERS/`, which stay on the cluster.
- `scaling` and `dsim-scaling` both contain pct 0 (empty population: synchronization only), 1, 3 and 10, with
  13 partition counts from 1 to 192. Every run has 10 iterations and there is one repetition per setting. Only rust
  also has `scoring = false`. No runs have `events = true` yet. `scaling` used matsim-rust 6960b40.
- `scaling-v2` is the same grid as `scaling` with the mobsim optimizations of matsim-rust (main at d41dba8, PRs #315
  and #316). Its time limits are twice the times measured in `scaling`. All 91 runs were submitted on 2026-10-16 (jobs
  9577809-9577900). `load.py` still reads `scaling`; switch it to `scaling-v2` after `fetch`.
- `~/scratch/rust-pt-routing` holds the older async-routing project. Its results are in
  `runs-svn/matsim-rust/async-routing-2026`.
- Tools on the cluster: `uv` and `python3` (`~/scratch/miniforge3/bin`), `svn`, `rsync` 3.2.7, Slurm. Locally, `rsync`
  is macOS openrsync (protocol 29). `--files-from` works with it, but avoid unusual filter syntax.

## Workflow

The details are in [README.md](README.md).

1. **Submit (on the cluster):** `uv run scripts/cluster/cluster.py [--settings scripts/cluster/cluster-dsim.toml] submit experiments/<x>.toml`.
   Always run `--dry-run` first and show the output.
2. **Monitor:** `squeue --me --name <name>`, `collect <name>`, logs in `runs/<run_id>/slurm-<jobid>.log`.
3. **Fetch (locally):** `uv run scripts/cluster/cluster.py [--settings ...] fetch <name>` runs `collect` on the
   cluster. It then copies the files listed in `FETCH_FILES` (in `cluster.py`) into runs-svn and runs `svn add`, but
   it does not commit. For experiments outside `out_root`, pass the path relative to the cluster repo, e.g.
   `fetch output/experiments/archive/scaling`. Check with `fetch --dry-run` first.
4. **Commit runs-svn:** only from the Mac, and only after the user agrees. Commit the target directory
   (`.../iterations-vs-dsim-2026`), not a single experiment, while the parent is still only scheduled for addition.
5. **Analyse** locally from the runs-svn copy, with the package `src/main/python/iterations` (see Analysis below).

- `fetch` runs the `cluster.py` that is checked out on the cluster. After changing `cluster.py`, the cluster repo
  needs a `git pull`; ask the user first.
- Use the settings file that matches the experiment: rust experiments use the default `cluster.toml`,
  DSim experiments use `cluster-dsim.toml`.
- DSim `runtimes-*/tasks.csv` (about 23 MB per run) is not fetched by default. Add it with `extra_files` in `[fetch]`
  only if the user wants it in svn.

## Rules

Fine without asking:
- Read-only commands: `ls`, `du`/`find` limited to the experiment directories, reading logs, `squeue`, `sacct`,
  `sinfo`.
- `submit --dry-run`, `collect` (rewrites only `runs.csv`), `fetch --dry-run` and `fetch` (copies into the local
  runs-svn and runs `svn add`, which `svn revert` undoes).

Ask first, every time:
- `submit` without `--dry-run` or plain `sbatch`, since it uses compute time. Every job takes a full `cpu-genoa`
  node (192 cores, `--exclusive`), so give the number of runs and the time limits.
- `scancel`.
- Deleting, moving or editing anything on the cluster.
- Git or svn operations that change something (pull, checkout, commit) on the cluster or in svn.
- Building (`cargo build --release`, `./mvnw package`), because it changes the binary that the next submissions use.
- Changing `out_root`. `submit` would no longer find the existing `manifest.csv` and would submit all runs again.

Always:
- Nothing heavy on login nodes: no simulations, no large analyses, no long parallel loops. Use `sbatch`, or
  `salloc -p cpu-genoa:test` for interactive work. Do not repeatedly `find` or `du` across all of `~/scratch` (shared
  Lustre file system).
- Stay in this project's directories. Do not read other users' or other projects' data, or secrets (`~/.ssh`, tokens).
  Everything I read is sent to the model provider.
- Pull data with `fetch`/rsync and analyse it locally, instead of mounting the cluster with sshfs.

## Known quirks

- **Memory accounting:** `sacct` does not report memory usefully on Lise (`jobacct_gather/linux`). The batch step
  shows `MaxRSS` 0 and step `.0` a few MB, so `max_rss_mb` in `runs.csv` is meaningless. Peak memory has to be
  measured in the job itself.
- **Absolute paths in older `runs.csv`:** `runs.csv` from older versions of `collect` has absolute cluster paths in
  `run_dir`. `fetch` rewrites them to `runs/<run_id>`.
- **DSim and scoring:** DSim always scores, so `scoring = false` is not supported.
- **Resubmitting:** `submit` only submits runs that are missing from `manifest.csv`. To resubmit a run, delete its
  line from `manifest.csv`.
- **Library version in `build_info.json`:** before 2026-10-15, `build_info.json` recorded this repository twice and not
  matsim-rust. For those runs, the matsim-rust commit is only known from the `Cargo.lock` on the cluster (`6960b40` on
  2026-10-15).

## Analysis

- `src/main/python/iterations/`:
  - `load.py` reads both experiments into the tables `runs` and `phases` (run x iteration x phase, plus the real-time
    ratio). Its docstring defines the phases and the real-time ratio.
  - `plots.py` holds the paper figures and their style.
  - `python -m iterations` writes all figures as PDF and PNG to
    `src/main/python/jupyter-notebooks/plots/iterations-vs-dsim/` (gitignored).
- Notebook: `src/main/python/jupyter-notebooks/iterations-vs-dsim.ipynb`.
- Commands, run in `src/main/python`: `uv run --group analysis python -m iterations` and
  `uv run --group analysis jupyter lab`. The `analysis` dependency group is in `pyproject.toml`.
- Definitions:
  - Real-time ratio = simulated seconds (36 h) / wall time of the simulation loop. rust: span `simulation::run` of
    rank 0. DSim: the ratio it logs per iteration, measured over the same loop.
  - The real-time ratio is the median over iterations 1-9, the phases over iterations 1-8. Iteration 0 includes the
    setup.
  - The 1-second stopwatch of DSim is not needed: the logfile timestamps have millisecond resolution.
- Colors: pct 1/3/10 use categorical blue, orange and aqua (validated for all pairs), and 0 % is gray. The axis
  label is "RTR"; the paper explains the details.
- Plot 1 is split into two figures:
  - 1a `rtr_no_agents`: only 0 %, with its own y axis. The maxima and the last values (192 partitions) are labeled.
  - 1b `rtr_vs_parts`: three panels side by side for 1/3/10 %, on the same y scale (the user explicitly wants that).
- Rust is red and DSim violet. The maximum of each line is marked with a ring and labeled (`compact`, e.g. 32.5k);
  `label_points` picks the label position automatically. The user found a single panel with all pct values too
  cluttered.
- Panel titles are bold, lines are 1 pt thin, and the y-grids of the RTR axes have major lines only. The user does not
  want pct labels written next to the lines; the legend identifies the pct.
- Plot 2 shows only the phase shares (rows: rust and DSim; columns: pct). The user removed the row with the wall time
  per iteration.
- Do not put the engine colors next to the pct or phase colors: rust red and the orange of 3 % or scoring cannot be
  told apart (validator FAIL).
- Plot 3 has one panel with all pct values (the user wants it that way, unlike plot 1). On the left are the RTR lines
  with scoring on and off. On the right is only the overhead in the mobsim (RTR off / RTR on - 1, iterations 1-9),
  not the whole iteration.
- Status (2026-10-15): the user approved plots 1 and 2. Plot 3 has been adjusted as requested, and plot 4 (events
  on/off) still needs runs.

## Rules of the computing center on LLM use

The NHR@ZIB user wiki (checked 2026-10-15) does not prohibit using LLMs or coding agents. Its VS Code page even
recommends GitHub Copilot on the cluster. I have not checked the binding terms of use that were accepted in the portal.
What applies: keys must have a passphrase, must be used only for Lise, and must never be shared or uploaded. No heavy
work on login nodes.
