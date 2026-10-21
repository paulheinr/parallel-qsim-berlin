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
  dependency (GitHub) and `Cargo.lock` pins its commit. Since 2026-10-21 (for scaling-v6) the dependency has
  `branch = "main-mode-neighbors"` and the lock pins c646f29c; before, main at e20838e. Remove the branch again
  for experiments with main. Locally it is a path dependency. Do
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
  experiments took about 1.06 TB, mostly `ITERS/` and plans. Cleanup on 2026-10-20, with the user's approval: deleted
  `ITERS/` and `output_plans.binpb` of all runs of both (about 940 GB; `output_experienced_plans.binpb` kept). Now
  scaling-v3 takes 29G and scaling-v3-gsync 25G.
- `scaling-v4` and `scaling-v4-gsync` repeat scaling-v3 and scaling-v3-gsync (same grids and time limits) with
  matsim-rust main at eec3c5f: #323 (spin-then-park barrier for global sync) and #324 (less scoring overhead in the
  mobsim, backpacking subscribes only to the event types it needs). Both use the binary `2e6d98a7a46b`. Submitted on
  2026-10-20: 91 runs of scaling-v4 (jobs 9588840-9588930) and 52 runs of scaling-v4-gsync (jobs 9588931-9588982),
  output in `output/experiments/submit-scaling-v4{,-gsync}.log`. Sums of the time limits are 50.8 and 58.5 node hours;
  scaling-v3 and scaling-v3-gsync used 10.1 and 7.6 node hours. All runs completed (exit 0) in 9.8 and 5.4 node hours
  and are in runs-svn (r6970). On the cluster they took 642G and 350G with `ITERS/` and plans; afterwards work used
  2.18 TiB of 3 TiB and 228k of 250k inodes (2026-10-20). Their `ITERS/` and plans were deleted before scaling-v5,
  see there.
  Results (one repetition per setting): #323 removes most of the cost of the barrier. At 0 %, RTR with global sync is
  4.79M at 1 partition (without 4.83M, scaling-v3-gsync 1.19M) and 36.1k at 192 (42.3k, 2.53k). With agents, global
  sync keeps 50-100 % of the RTR without it (lowest at 10 %, 96-192 partitions), and from 4 partitions on rust with
  global sync is 1.1-3.4 times as fast as DSim. #324 cuts the scoring cost per step at 1-8 partitions by about a third
  (overhead at 10 %: 37-43 % before, 23-29 % now). Without scoring, RTR is within 7 % of scaling-v3 up to 64
  partitions and within -10 %/+18 % at 96-192 (0 % differs as much there, so that is run-to-run noise). Open: with
  scoring on, 1 % and 3 % at 32-192 partitions are often 10-40 % slower than in scaling-v3 (1 % at 96: 40.9k
  instead of 66.2k). At 64-192 partitions, the scoring costs 5-17 us per step there in v4, about as much as at 10 %
  (11-19 us), but 1-6 us in v3. All those 1 % runs ran on genoa1230, the 3 % ones on several nodes. Repetitions
  would show whether #324 added a fixed cost per step. Cause found: commit 3e477073 of #324, see `pr324`, `poll`
  and `revert` below.
- `scaling-v5` and `scaling-v5-gsync` repeat scaling-v4 and scaling-v4-gsync (same grids and time limits) with
  matsim-rust main at e20838e: #326 (revert of 3e477073) and #325 (xml crate 1.4.0, only the XML events writer and a
  test). Both use the binary `a841419d22ae`. Submitted on 2026-10-20: 91 runs of scaling-v5 (jobs 9591312-9591402)
  and 52 runs of scaling-v5-gsync (jobs 9591403-9591454), output in `output/experiments/submit-scaling-v5{,-gsync}.log`.
  All runs completed (exit 0) in 10.0 and 5.6 node hours; fetched on 2026-10-21 and in runs-svn (r6971).
  Results (one repetition per setting; ratios of the median RTR):
  - The revert works: with scoring on at 32-192 partitions, v5 is 1.13-1.90x as fast as v4 at 1 % and 1.04-1.39x at
    3 % (except 3 % at 96, 32.7k, a single run with iterations from 30.9k to 40.6k), and as fast as or faster than
    v3 (1 % at 96: 77.5k, v4 40.9k, v3 66.2k). Scoring overhead in the mobsim at 32-192 partitions: 1 % 4-15 %
    (v3 8-32 %, v4 14-114 %), 10 % 20-26 % (v3 26-35 %).
  - At 1-4 partitions, the smaller backpacks did help: overhead at 10 % 30-36 % in v5, 23-29 % in v4, 37-40 % in v3;
    v5/v4 at 10 % scoring on is 0.90 (P=1), 0.95 (2), 0.91 (4). So the rest of #324 gains little at P=1 on Genoa;
    most of its gain at few partitions came from 3e477073.
  - 0 % and scoring off: unchanged against v3 and v4 (differences within run-to-run noise).
  - Global sync: v5-gsync is 1.11-1.50x as fast as v4-gsync at 1 % from 16 partitions and 1.06-1.26x at 3 %, about
    the same at 10 %. From 8 partitions it keeps 73-92 % of the RTR without global sync at 1 % and 79-105 % at
    3 %; at 10 % only 40-77 % from 64 partitions. Maxima: 1 % 56.7k (without 77.5k), 3 % 33.2k (40.2k), 10 % 11.4k (19.3k); DSim
    13.7k, 9.02k, 5.05k.
- Cleanup before scaling-v5 (2026-10-20, with the user's approval; before it 2.37 TiB and 239.8k inodes): deleted
  `ITERS/` and `output_plans.binpb` of all runs of scaling-v4 and scaling-v4-gsync (941 GB, now 29G and 25G) and of
  `output/commits/{pr324,poll,revert}` (134 GB, now 3.7G, 3.7G and 6.8G), and `output/commits/revert/build` (836
  files). That freed only about 2.4k inodes; each pair of scaling experiments adds about 11.8k (only about 900 of
  them in `ITERS/`), so the inode limit of 250k is close. Most inodes are outside this project.
- Fewer neighbors and better balance (2026-10-21, the user asked for it, see `neighbors_vs_parts` below):
  - matsim-rust branch `main-mode-neighbors` (local worktree `~/git/parallel_qsim_rust_worktrees/main-mode-neighbors`,
    on top of e20838e): 5f87d084 `SimNetworkPartition::find_neighbors` ignores links that allow modes but no main mode
    (pt is teleported), and `MetisOptions::min_conn` sets METIS's MinConn; c646f29c `imbalance_factor` is METIS's
    load imbalance (1.1 = 10 %; before, 1.1 became ufactor 1100, i.e. up to 2.1 times the mean). `metis.yml` now says
    2.1, which reproduces the networks `metis.<P>` with the new code.
  - New networks `berlin-v7.1.network.metis-minconn-const.<P>.xml.zst` (`input/partitioning/metis-minconn-const.yml`:
    MinConn, constant edge weights, imbalance 1.1), created locally with `partition_networks` built against the
    branch (a copy of `src/main/rust` with the path dependency pointing to the worktree; that build reproduces
    `metis.096` exactly). Copied into the local shared-svn on 2026-10-21; the user commits them to svn and updates
    the cluster.
  - Compared (main-mode neighbors max at 96 / 192, links of the largest partition / mean, traffic of the busiest
    partition / mean): metis 14 / 13, 1.43 / 1.55, 3.5 / 4.6; MinConn with capacity weights 11 / 13; MinConn with
    constant weights 8 / 9, 1.05 / 1.04, 2.4 / 3.5. Traffic as vertex weight (`PreComputed`, node attribute
    `cmp_weight` = vehicles per day on the in-links from the MATSim 1pct `output_links.csv.gz`, without the pt links,
    which carry half of MATSim's volume) balanced the traffic to 1.08 at 9 / 9 neighbors, but the user rejected it:
    the volumes are not known beforehand and it is too complicated.
  - `scaling-v6` (`experiments/scaling-v6.toml`): only that network, 1pct, scoring on, events off, rust only, 13
    runs, time limits of v5 (30 min at 1-2 partitions, else 15).
- `scripts/cluster/hotpath.sh [name]` (2026-10-20, written because the user finds rust at many partitions
  unsatisfying): builds with `--features hotpath` into `src/main/rust/target/hotpath` (not `target/release`) and runs
  10 cases in one job on one node: 1 % and 3 % at 32/96/192 partitions with hotpath (scoring on, at 96 also off), and
  the plain binaries of scaling-v4 and scaling-v3 at 1 %, 96 partitions, scoring on. Output in
  `output/hotpath/<name>/` (outside `out_root`, no `manifest.csv`, not fetched by `fetch`; rsync command in the
  script header). `hotpath.json` sums each function over all threads, so it shows no imbalance between partitions;
  waiting for the neighbors is in `message_broker::send_recv`.
- `hotpath-v4b` (job 9590091, 2026-10-20, 28 min on genoa1143, all 10 cases exit 0; 34G on the cluster, fetched
  without plans to the gitignored local `output/hotpath/hotpath-v4b`, not in svn). `hotpath-v4` is the first
  submission (job 9590088, 2G), which ran only its first case: `srun` swallowed the list of cases on stdin (fixed
  in 183d301). Results:
  - Same node, 1 %, 96 partitions, scoring on, plain binaries: v4 RTR 48.9k (45.3k in hotpath-v4), v3 70.9k. So
    the slowdown of scaling-v4 is the code, not genoa1230. Without global sync, #323 only adds the barrier at the
    end of the mobsim, so it comes from #324 (without scoring, scaling-v4 was not slower).
  - hotpath wraps the partition channels, which costs a lot: RTR 2.3x lower at 96 partitions, 3x at 192, 1.25x at
    32; `send_recv` is 90-96 % of `do_sim_step` there and mostly measures that. Do not use these runs for RTR.
  - The work of a partition outside `send_recv` is tiny: 3 µs per step at 1 % and 96 partitions, 5 µs at 3 %
    (move_nodes + move_links about 1.4 and 3.3 µs). Without agents, a step takes 9.9 µs at 96 partitions (scaling-v4,
    0 %). At many partitions the mobsim is bound by the synchronization and the waiting for the slowest neighbor.
  - Scoring as computation is small: at 1 %, 96 partitions, the backpacking functions take 4 s and the scoring
    handlers about 18 s more in `process_event` (190 ns per event, 95M events), summed over all threads and 10
    iterations, i.e. about 25 ms per partition and iteration. Without hotpath, scoring costs 1.2-1.7 s per
    iteration of the mobsim there (scaling-v4: 3.17 s with, 1.48 s without scoring; plain v4 on genoa1143: 2.65 s
    with scoring). So scoring slows the mobsim through waiting, not through its own work. A guess, not checked: partitions poll for 50 µs (`POLL_BEFORE_BLOCKING`) and then block,
    so slightly longer steps of busy partitions cause blocking and slow wake-ups that spread to the neighbors.
  - `process_event` per event gets slower with more partitions at the same number of events (1 %: 289 ns at 32,
    413 at 96, 719 at 192 partitions).
  - The commits of #324 were compared in `pr324`, see below.
- `scripts/cluster/commits.sh [name]` (2026-10-20): builds berlin_iterations_v7 without hotpath for several
  matsim-rust commits (`COMMITS`), from a copy of `src/main/rust` in `output/commits/<name>/build` with matsim-rust
  `{ git, rev }` and its own target dir (`src/main/rust`, its Cargo.toml/Cargo.lock and `target/release` are not
  touched), and runs `CASES` x `REPETITIONS` in one job on one node, the repetitions interleaved. Output in
  `output/commits/<name>/` (outside `out_root`; rsync command in the script header). The build dir (7.3k files,
  3.4G) is not needed once the binaries are in `bin/`; delete it after asking.
- `pr324` (job 9590368, 2026-10-20, 21 min on genoa1244, all 20 runs exit 0; build dir deleted with the user's
  approval, 39G and 2.4k files left on the cluster; fetched without plans to the gitignored local
  `output/commits/pr324`, not in svn): 1 %, 96 partitions, run.env of scaling-v4, two repetitions. RTR (median of
  iterations 1-9) of the two repetitions, scoring on: f91a7b2 63.5k/73.5k (scaling-v3 binary 71.7k/70.6k),
  47cb835c (#323 merged) 67.2k/70.3k, 2c4135cf 69.2k/71.3k, 99a27380 69.1k/70.9k, 3e477073 55.8k/61.0k, f2f49a27
  46.5k/51.9k (= eec3c5f; scaling-v4 binary 54.7k/51.2k). Scoring off: v3 77.1k/82.4k, v4 81.7k/81.0k.
  - The slowdown comes from 3e477073 (smaller backpacks and vehicle occupants). All 5 binaries before it (each with
    its own code layout) reach 66.9-70.9k (medians of 18 iterations), all 3 from it on 47.7-58.3k (3e477073 58.3k,
    f2f49a27 47.7k, v4 binary 52.1k): about -24 % on average. If the layout alone spread the binaries at random, the
    3 slowest would be exactly these 3 with a chance of 1 in 56. #323, 2c4135cf and 99a27380 do not change the RTR.
  - Iteration 0, where all builds start from the same plans, shows the same split (before 3e477073 mostly
    51-58k, from it on 38-48k). So it is the mobsim itself, not other plans through scoring and replanning.
  - f2f49a27 only removes `Backpack::handle_event` and `PartialPlan::handle_event`, which only tests call, so the
    code that runs is that of 3e477073 (in the binaries, only 24 of 5.9k functions differ: TypeId constants, which
    depend on the rev, and unrelated code; 47 of the 242 functions of the mobsim, events and scoring sit at another
    alignment). It was 18 % slower than 3e477073 here, but not in `poll` on another node (59.3k vs. 57.3k), so that
    was run-to-run noise, not the code layout. From 3e477073 on, runs of the same binary spread much more (in
    `poll`, 3e477073: 63.1k and 51.5k) than before (99a27380: 69.1-72.7k in four runs on two nodes).
  - Not understood: from the code, 3e477073 should make backpacking cheaper, and hotpath shows that the backpacking
    work is small. It (a) boxes `pt_description` in `PartialRoute` (one allocation per pt leg) and (b) replaces the
    `IntSet` of the persons per vehicle by `VehicleOccupants` (first person inline, others in a `Vec`; no allocation
    per vehicle). Blocking does not explain it, see `poll`.
- `poll` (job 9590823, 2026-10-20, 23 min on genoa1168, all 20 runs exit 0; target dir deleted by the script,
  outputs on the cluster, fetched without plans to the gitignored local `output/commits/poll`, not in svn): 99a27380,
  3e477073 and f2f49a27 with `POLL_BEFORE_BLOCKING` = 10 ms instead of 50 us (partitions practically never block),
  built from a changed copy of cargo's checkout (path dependency), against the binaries of pr324. Two repetitions,
  RTR as median of the 18 iterations 1-9 of both, 50 us -> 10 ms:
  - 1 %, 96 partitions, scoring on: 99a27380 71.7k -> 60.6k, 3e477073 56.1k -> 50.0k, f2f49a27 58.9k -> 49.5k.
    Scoring off, 99a27380: 78.8k -> 73.7k. 1 %, 192 partitions, scoring on, f2f49a27: 25.5k -> 26.3k.
  - Longer polling does not help: at 96 partitions all builds get 6-16 % slower, at 192 nothing changes. So
    blocking and slow wake-ups are not what limits the mobsim there (the guess from hotpath-v4b is wrong). Why
    polling costs is not checked (maybe lower clock rates of the busy cores, or contention on the channels).
  - With 10 ms, 3e477073 is still 17 % slower than 99a27380. So its slowdown is not amplified by blocking, and the
    gap of 99a27380 to 3e477073 is reproduced on a second node (71.7k vs. 56.1k with 50 us).
- `revert` (job 9591134, 2026-10-20, 36 min on genoa1054, all 28 runs exit 0; outputs on the cluster, fetched
  without plans to the gitignored local `output/commits/revert`, not in svn): eec3c5f (= scaling-v4) with all of
  3e477073 taken back (`patches/revert-3e477073.patch` = `git diff 3e477073 99a27380 -- matsim_rust/src`; the scoring
  unit tests and `test_scoring`, incl. the reference experienced plans of equil, pass), `eec3c5f_copy` built the same
  way without the patch, and binaries of pr324. RTR as median of iterations 1-9 of all repetitions, scoring on:
  - 1 %, 96 partitions, 4 repetitions: revert 70.6k (66.1-74.1k per run), eec3c5f_copy 47.3k (43.3-56.5k),
    f2f49a27 54.2k, 99a27380 73.2k, f91a7b2 68.5k.
  - 3 %, 96 partitions: revert 40.5k, f2f49a27 34.2k (+18 %). 1 %, 192 partitions: revert 34.4k, f2f49a27 26.2k
    (+31 %). For comparison (other nodes, one run): scaling-v3 66.2k / 38.1k / 33.0k, scaling-v4 40.9k / 33.4k /
    27.1k, DSim 13.4k / 8.4k / 11.0k.
  - So 3e477073 causes the slowdown of scaling-v4 with scoring on, and taking it back restores the RTR of
    scaling-v3 (and the small spread between runs). Which of its two changes, (a) or (b), is responsible is not
    known. The revert is matsim-vsp/matsim-rust#326, merged on 2026-10-20 (main e20838e) and measured in
    `scaling-v5`. Not measured here: few partitions (P=1-8), where #324 had measured a gain of the smaller backpacks
    on a laptop.
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
    The maxima and the values at 1 partition are marked with rings and labeled. Each panel also shows the 0 % lines
    of rust and DSim muted (engine color, alpha 0.4, thinner, no markers or labels, legend "Rust, 0 %"), as the upper
    limit of the runs with agents (the user wants that, 2026-10-21). They must not change the y scale, which comes
    from the data with agents; above it they are clipped (rust 0 % enters at about 16 partitions).
- Every figure has the experiments and their library versions in small print below its lower right corner (the user
  wants that, 2026-10-20): `setting` in `load.py` (from `build_info.json`, for DSim from the jar name), `SETTING_NOTE`
  in `plots.py`. Turn it off for the paper.
- `neighbors_vs_parts` (2026-10-21, the user asked for it): neighbors per partition of the 13 networks of the runs
  (`berlin-v7.1.network.metis.<P>.xml.zst` in shared-svn, the same for rust and DSim), computed by
  `iterations/partitions.py` from the local checkout (all 13 in about 10 s; `neighbors_of` for any set of networks,
  optionally with `link_volumes` for the traffic per partition). One dot per partition, rows of dots side by side
  (width = count), lines for mean and maximum, and muted lines for other maxima (`references`); equally spaced
  partition counts (128/144/192 too close on a log axis). `column`: `neighbors` (any link, matsim-rust up to e20838e)
  or `neighbors_main_modes` (as on the branch main-mode-neighbors).
  - Mean about 7 from 16 partitions on, but the maximum grows: 11 (16), 16 (24), 20 (96, 128), 25 (144), 26 (192).
    pt links (mode pt only, a quarter of the 284k links) make a fifth of the neighbor pairs (136 of 665 at 192);
    without them the maximum is 13-15. METIS balances the number of links (InLinkCount), not the traffic, and
    nothing limits the neighbors of a partition (matsim-rust sets UFactor, Seed and Contig, not MinConn).
  - Without agents, the wall time per step of rust (1/RTR) is about 0.5 us per neighbor of the partition with the
    most neighbors up to 96 partitions (0.41-0.61; correlation 0.97 with the maximum, 0.89 with the mean), and rises
    to 0.62 (128), 0.66 (144) and 0.94 us (192) beyond one socket. DSim: 2.0-3.0 us per neighbor. So the slowest
    partition sets the pace (every partition waits for all of its neighbors in every step), and 1 % is bound by
    this from about 64 partitions on (step 12.9 us at 96 and 29.7 at 192, of which 9.9 and 24.3 at 0 %).
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
- Status (2026-10-21): the analysis uses `scaling-v5` (`EXPERIMENTS` in `load.py`). `python -m iterations` also
  writes plots 1a and 1b with global sync as `rtr_no_agents_gsync` and `rtr_vs_parts_gsync` (`GSYNC_EXPERIMENTS`:
  `scaling-v5-gsync` and `dsim-scaling`, legend "Rust, global sync"), if these experiments are fetched. Do not load
  `scaling-v5` and `scaling-v5-gsync` (or v4 with v4-gsync, v3 with v3-gsync) together into the plots: both have rust
  runs with the same pct/parts/scoring, and the plot functions do not separate them by `global_sync`. Older figures:
  `--experiments scaling-v4 dsim-scaling --gsync-experiments scaling-v4-gsync dsim-scaling` (same for v3). Plot 4 (events on/off)
  still needs runs.

## Rules of the computing center on LLM use

The NHR@ZIB user wiki (checked 2026-10-15) does not prohibit using LLMs or coding agents. Its VS Code page even
recommends GitHub Copilot on the cluster. I have not checked the binding terms of use that were accepted in the portal.
What applies: keys must have a passphrase, must be used only for Lise, and must never be shared or uploaded. No heavy
work on login nodes.
