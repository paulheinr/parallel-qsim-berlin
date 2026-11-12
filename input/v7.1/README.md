# Berlin v7.1 configs

| Files | Engine | Used by |
|---|---|---|
| `berlin-v7.1.<pct>pct.config.yml` | rust | scaling experiments up to scaling-v6 (binpb inputs) |
| `berlin-v7.1.<pct>pct.{pt,nopt}.config.yml` | rust | validation rust vs. DSim, later the new benchmark |
| `berlin-v7.1-<pct>pct.{pt,nopt}.dsim.config.xml` | DSim, QSim | the same (QSim with `controller.mobsim=qsim`) |
| `berlin-v7.1-0pct.plans.xml`, `berlin-v7.1.0pct.config.yml` | both | 0pct runs (empty population) |

The `pt` and `nopt` configs of rust and DSim read the same files (see `readme.txt` in
`shared-svn/projects/rust-qsim/berlin-v7.1/` for how the prepared ones were made):

- network `shared-svn/.../network/berlin-v7.1.network.metis-minconn-const.008.xml.zst` (8 partitions, DSim with
  `dsim.partitioning = none`),
- vehicles and facilities of `public-svn/.../calibrated-<pct>pct/output`,
- `pt`: the calibrated output plans, transit schedule and transit vehicles; rust uses `ScheduleBasedTeleportation`, DSim
  simulates the pt vehicles on the network,
- `nopt`: `shared-svn/.../<pct>pct/berlin-v7.1-<pct>pct.plans-nopt.xml.gz` (persons whose selected plan uses pt removed),
  no transit,
- scoring parameters `shared-svn/.../<pct>pct/berlin-v7.1-<pct>pct.scoring.xml`.

Both keep only the selected plan of each person (in the code of `berlin_iterations_v7` and `OpenBerlinDSimBenchmark`).
Both: main modes car, freight and truck (bike and ride are teleported along their network routes), walk 1.23 m/s with a
beeline factor of 1.3, kinematicWaves and PassingQ, stuck time 30 s, end time 36:00, ReRoute 0.2 / SelectExpBeta 0.8 for
all subpopulations (in `berlin_iterations_v7` and in the DSim configs), no innovation switch-off and no score MSA.

rust writes no trips file. `TripsAndLegsCsvWriter` (MATSim 2027.0-PR5260, in the matsim-berlin jar) writes
`output_trips.csv.zst` and `output_legs.csv.zst` from its `output_experienced_plans.xml.zst`. DSim writes
`berlin-v7.1-<pct>pct.output_trips.csv.zst` itself (MATSim 2027 compresses with zstd; `controller.writeTripsInterval` must be
greater than 0, the configs use 1000).

## Local runs

Run from the repository root. Build first: `cargo build --release` in `src/main/rust`, and `./mvnw clean package -DskipTests`
in `../matsim-berlin` (branch `ph/v7.1.1-dsim`). Paths in `--set` are relative to the config unless absolute.

```shell
JAR=$(ls -t ../matsim-berlin/matsim-berlin-7.1-SNAPSHOT-*.jar | head -1)
SCORING=../../shared-svn/projects/rust-qsim/berlin-v7.1/1pct/berlin-v7.1-1pct.scoring.xml
```

it0 (only the mobsim with the calibrated plans), e.g. queue and FIFO:

```shell
src/main/rust/target/release/berlin_iterations_v7 --config input/v7.1/berlin-v7.1.1pct.pt.config.yml 8 \
  --set output.output_dir=$PWD/output/validation/rust-1pct-pt-queue-fifo/output \
  --set qsim.traffic_dynamics=queue --set qsim.link_dynamics=fifo
java -cp $JAR org.matsim.application.analysis.population.TripsAndLegsCsvWriter \
  --run-directory output/validation/rust-1pct-pt-queue-fifo/output

java -Xmx40G --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp $JAR org.matsim.run.dsim.OpenBerlinDSimBenchmark \
  --config input/v7.1/berlin-v7.1-1pct.pt.dsim.config.xml --threads 8 --scoring-config $SCORING \
  --output $PWD/output/validation/dsim-1pct-pt-queue-fifo/output \
  --config:dsim.trafficDynamics=queue --config:dsim.linkDynamics=FIFO
```

it100 (iterations 0 to 100 from plans without routes, innovation off and score MSA from iteration 90), seed 1:

```shell
PLANS=$HOME/shared-svn/projects/rust-qsim/berlin-v7.1/1pct/berlin-v7.1-1pct.plans-nopt-noroutes.xml.gz

src/main/rust/target/release/berlin_iterations_v7 --config input/v7.1/berlin-v7.1.1pct.nopt.config.yml 8 \
  --set output.output_dir=$PWD/output/validation/rust-1pct-it100-seed1/output --set population.path=$PLANS \
  --set controller.last_iteration=100 --set computational_setup.random_seed=1 \
  --set replanning.fraction_of_iterations_to_disable_innovation=0.9 --set scoring.fraction_of_iterations_to_start_score_msa=0.9
java -cp $JAR org.matsim.application.analysis.population.TripsAndLegsCsvWriter \
  --run-directory output/validation/rust-1pct-it100-seed1/output

java -Xmx40G --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp $JAR org.matsim.run.dsim.OpenBerlinDSimBenchmark \
  --config input/v7.1/berlin-v7.1-1pct.nopt.dsim.config.xml --threads 8 --scoring-config $SCORING \
  --output $PWD/output/validation/dsim-1pct-it100-seed1/output --config:plans.inputPlansFile=$PLANS \
  --config:controller.lastIteration=100 --config:global.randomSeed=1 \
  --config:replanning.fractionOfIterationsToDisableInnovation=0.9 --config:scoring.fractionOfIterationsToStartScoreMSA=0.9
```

MATSim's QSim as a reference runs with the same jar and config as DSim, with the mobsim switched and the dynamics set
in `qsim` instead of `dsim` (12 threads as in the calibrated runs), e.g. it0 with kinematicWaves and PassingQ:

```shell
java -Xmx40G --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp $JAR org.matsim.run.dsim.OpenBerlinDSimBenchmark \
  --config input/v7.1/berlin-v7.1-1pct.pt.dsim.config.xml --threads 8 --scoring-config $SCORING \
  --output $PWD/output/validation/qsim-1pct-pt-kw-pq/output --config:controller.mobsim=qsim \
  --config:qsim.numberOfThreads=12 --config:qsim.trafficDynamics=kinematicWaves --config:qsim.linkDynamics=PassingQ
```

On the cluster, the experiments `validation-*`, `dsim-validation-*` and `qsim-validation-*` run the same commands
through `scripts/cluster/cluster.py` (settings `cluster-validation.toml`, `cluster-validation-dsim.toml` and
`cluster-validation-qsim.toml`). The figures of the comparison are written by `python -m validation --experiment ...`
in `src/main/python` into runs-svn `iterations-vs-dsim-2026/plots/`.
