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
  dependency (GitHub) and `Cargo.lock` pins its commit (f91a7b2 since 2026-10-18). Locally it is a path dependency. Do
  not overwrite these changes. To build a newer matsim-rust from main on the cluster:
  `cargo update -p matsim-rust && cargo build --release` in `src/main/rust` (ask first, see Rules). Cargo is in
  `~/.cargo/env`; the build takes about half a minute.
- To rerun an experiment with a newer library and keep the old runs, give it a new name (a copy of the experiment file,
  e.g. `scaling-v2.toml`). Reusing the name submits nothing, because all runs are already in `manifest.csv`.
- New experiments get a `comment = """..."""` (since 2026-10-18): what they are for and what changed compared to the
  earlier ones. `submit` writes it with the binaries and commits to `description.md`, `fetch` copies that. Older
  experiments have no `description.md`; their purpose is in the header comments of their toml.
- Experiments on the cluster on 2026-10-16: `example`, `scaling` (29 GB), `scaling-v2` (26 GB) and `dsim-scaling`
  (12 GB), plus `scaling-v3` since 2026-10-18. Almost all of the size is plans, events and `ITERS/`, which stay on
  the cluster and are not fetched.
- Quota: `show-quota` (cached, updated every few minutes). Work (`/scratch/usr/bemheinr`) has a soft limit of 3 TiB
  and 250k inodes (hard 30 TiB, 1.5 M), with a grace period of 7 days. A finished 10pct run takes about 20 GB, mostly
  `ITERS/it.{0,9}` (13G) and `output_plans.binpb` (5G).
- Cleanup on 2026-10-16 (3.02 TiB used, after `scaling-v2`), with the user's approval: deleted
  `experiments/archive/scaling` (470G, the first submission of scaling on 2026-10-14; its results were fetched to
  runs-svn `archive/scaling` first, committed in r6968 on 2026-10-19), `output/v7.1` (342G, manual runs from 2026-10-04)
  and `ITERS/` and `output_plans.binpb` of all finished runs of `scaling` and `scaling-v2` (about 1.2 TB). Afterwards
  about 1.1 TB was used, of which `~/scratch/rust-pt-routing` is 892G (outputs from March 2026). The four pending
  `scaling-v2` runs will write `ITERS/` and plans again.
- `scaling` and `dsim-scaling` both contain pct 0 (empty population: synchronization only), 1, 3 and 10, with
  13 partition counts from 1 to 192. Every run has 10 iterations and there is one repetition per setting. Only rust
  also has `scoring = false`. No runs have `events = true` yet. `scaling` used matsim-rust 6960b40.
- `scaling-v2` is the same grid as `scaling` with the mobsim optimizations of matsim-rust (main at d41dba8, PRs #315
  and #316). Its time limits are twice the times measured in `scaling`. All 91 runs were submitted on 2026-10-16 (jobs
  9577809-9577900). 87 of them are in runs-svn (r6964); the four 10pct runs with 1 and 2 parts finished later
  (queue empty on 2026-10-18) and are not fetched yet.
  The analysis reads `scaling-v2` by default; `python -m iterations --experiments scaling dsim-scaling` gives the old
  figures.
- `scaling-v3` is the same grid and time limits as `scaling-v2` with matsim-rust main at f91a7b2 (PRs #317-#321, see
  its `description.md`). All 91 runs were submitted on 2026-10-18 (jobs 9582645-9582735); the output of `submit` is in
  `output/experiments/submit-scaling-v3.log` on the cluster. In `scaling-v2`, the 87 runs took 7.7 node hours.
  All runs completed (exit 0) and are in runs-svn (r6967).
- `scaling-v3-gsync` is the scaling-v3 grid with scoring on only and `global_sync = true` (optional grid key, rust
  only; run ids end in `_gsync-on_r1`). It is compared with the runs with scoring on of `scaling-v3` and uses the same
  binary (`9374a1fbd8b4`, f91a7b2). Time limits: those of scaling-v3, but at least 1 h. All 52 runs were submitted on
  2026-10-18 (jobs 9584171-9584222, output in `output/experiments/submit-scaling-v3-gsync.log`). All runs completed
  (exit 0) and are in runs-svn (r6967). Results: without agents, the barrier costs about 0.6 us per step at 1 partition
  (RTR 1.19M instead of 4.77M) and about 0.4 ms at 192 (2.53k instead of 42.6k). With agents, 1 partition matches
  scaling-v3, the maximum moves to 16-48 partitions, and from about 64 partitions rust is slower than DSim.
- After scaling-v3 and scaling-v3-gsync (2026-10-19), work used 2.13 TiB of 3 TiB and 217k of 250k inodes. The two
  experiments take about 1.06 TB, mostly `ITERS/` and plans.
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
  - 1a `rtr_no_agents`: only 0 %, with its own y axis. The maxima and the last values (192 partitions) are marked
    with rings and labeled.
  - 1b `rtr_vs_parts`: three panels side by side for 1/3/10 %, on the same y scale (the user explicitly wants that).
    The maxima and the values at 1 partition are marked with rings and labeled.
- Rust is red and DSim violet. The maximum of each line is marked with a ring and labeled (`compact`, e.g. 32.5k).
  Labels are in a white box framed in the line color. `label_points` picks the label position automatically; the
  x axes extend beyond 192 partitions so that labels of points there can sit centered next to them (the user found
  labels shifted to the left odd). The user found a single panel with all pct values too cluttered.
- Panel titles are bold, lines are 1 pt thin, and the y-grids of the RTR axes have major lines only. The user does not
  want pct labels written next to the lines; the legend identifies the pct.
- Plot 2 is `phase_lines` (chosen 2026-10-16): median seconds per iteration over iterations 1-8 of mobsim, scoring
  and replanning (`TIMED_PHASES`, the user wants `other` left out), one row of panels (one per pct) with one fixed log
  y axis for all, color = phase, rust solid with circles and DSim dashed with squares as in plot 1, lines 1 pt as in
  plot 1, values below 1 ms left out. The user rejected the phase shares (no absolute reference), stacked bars in
  seconds, and separate rows for rust and DSim; those functions are removed.
- Phases of rust come from `instrument_process_controller.csv`: `run_mobsim_phase` (since matsim-rust d41dba8, so
  `scaling-v2` and later; it includes `prepare_for_mobsim`, `split_for_mobsim` and collecting the agents, 0.3-1.6 s more
  than `simulation::run`, growing with the agents), `run_scoring_phase` and `run_replanning_phase`. They follow each
  other without gaps, so `other` is about 0 in rust.
- `other` of DSim (from the logfile timestamps): setup of the mobsim before the loop (PersonPrepareForSim, one LP per
  partition created anew every iteration) and teardown plus after-mobsim listeners, growing with the partitions (about
  6 s at 192 partitions, also at 0 %), and the analyses at the end of the iteration (ModeStats, ScoreStats, ...,
  about 1.2 s at 10 %). So the mobsim of DSim in plot 2 is only its loop, while that of rust includes its setup.
- Do not put the engine colors next to the pct or phase colors: rust red and the orange of 3 % or scoring cannot be
  told apart (validator FAIL).
- Plot 3 has one panel with all pct values (the user wants it that way, unlike plot 1). On the left are the RTR lines
  with scoring on and off. On the right is only the overhead in the mobsim (RTR off / RTR on - 1, iterations 1-9),
  not the whole iteration.
- Status (2026-10-19): the analysis uses `scaling-v3` (`EXPERIMENTS` in `load.py`). `python -m iterations` also
  writes plots 1a and 1b with global sync as `rtr_no_agents_gsync` and `rtr_vs_parts_gsync` (`GSYNC_EXPERIMENTS`:
  `scaling-v3-gsync` and `dsim-scaling`, legend "Rust, global sync"), if these experiments are fetched. Do not load
  `scaling-v3` and `scaling-v3-gsync` together into the plots: both have rust runs with the same pct/parts/scoring,
  and the plot functions do not separate them by `global_sync`. Plot 4 (events on/off) still needs runs.

## Rules of the computing center on LLM use

The NHR@ZIB user wiki (checked 2026-10-15) does not prohibit using LLMs or coding agents. Its VS Code page even
recommends GitHub Copilot on the cluster. I have not checked the binding terms of use that were accepted in the portal.
What applies: keys must have a passphrase, must be used only for Lise, and must never be shared or uploaded. No heavy
work on login nodes.
