# Integration tests: Rust simulation and router

Each directory is a scenario: the router of this repository and a matsim-rust simulation run as separate processes
(`process-compose.yml`), and `compare_events` compares the events with `expected/events/`. The run fails if the
router does not start, the simulation fails or the events differ.

Run from the repository root:

```shell
ROUTER_JAR=parallel-qsim-berlin-1.0-<commit>.jar \
SIM_BIN=<matsim-rust>/target/release/local_qsim_routing \
COMPARE_BIN=<matsim-rust>/target/release/compare_events \
  process-compose --no-server up -t=false -f integration/pt-tutorial-dummy/process-compose.yml
```

`ROUTER_JAR` comes from `./mvnw package -DskipTests`. Build the binaries from matsim-rust at the revision that
`src/main/rust/Cargo.lock` pins. `process-compose` and `grpcurl` must be on the `PATH`.

On a Slurm cluster, use `sbatch --export=ROUTER_JAR=...,SIM_BIN=...,COMPARE_BIN=... integration/<scenario>/slurm.sh`. This is a heterogeneous job
with the router and the simulation on nodes of their own; the script header has the details.

After an intended change, replace `expected/events/` with the uncompressed events of the run
(`output/integration/<scenario>/sim/events/`) and check the diff.

CI: the job `integration` in `.github/workflows/ci.yml`. To add a scenario, add an entry to its matrix.
