#!/bin/bash --login
#SBATCH --partition=cpu-genoa
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --exclusive

# Runs a single simulation run. All parameters are read from <run_dir>/run.env, which
# scripts/cluster/cluster.py writes before submitting. Time limit, job name and log file are set by cluster.py.
#
#   sbatch [--time=...] scripts/cluster/run-sim.sh <run_dir>
#   scripts/cluster/run-sim.sh <run_dir>          # without Slurm, e.g. as a local smoke test
#
# run.env defines BIN, CONFIG, NUM_PARTS, SCORING_MODE (enabled|disabled), WRITE_EVENTS (none|file) and
# optionally NETWORK (pre-partitioned network), LAST_ITERATION (0-based, inclusive), TRAFFIC_DYNAMICS (queue |
# kinematicWaves), LINK_DYNAMICS (FIFO | PassingQ), SEED (random seed), PLANS (population file) and EXTRA_ARGS (bash
# array of additional arguments, appended last). Unset optional values leave the value of the config.
#
# rust: with TRIPS_JAR (a matsim-berlin jar), MATSim's TripsAndLegsCsvWriter writes output_trips.csv.zst and
# output_legs.csv.zst from the experienced plans after a successful simulation, in the same job.
#
# With ENGINE=dsim (set in cluster-dsim.toml), BIN is the matsim-berlin jar and the run is done with DSim. Optional:
# PLANS, VEHICLES and FACILITIES (otherwise those of the config), SCORING_CONFIG (--scoring-config of
# OpenBerlinDSimBenchmark), JAVA, JAVA_OPTS and RUN_ID (prefix of the output files).
#
# With ENGINE=qsim (set in cluster-validation-qsim.toml), the same jar and DSim config run with MATSim's QSim
# (controller.mobsim=qsim) and QSIM_THREADS threads (qsim.numberOfThreads); TRAFFIC_DYNAMICS and LINK_DYNAMICS then set
# qsim.* instead of dsim.*. NETWORK still works: QSim ignores the partition attributes, and --threads NUM_PARTS keeps
# the partition check of OpenBerlinDSimBenchmark happy.
#
# At the end, result.json is written into the run directory (also on failure, scancel and time limit). With TRIPS_JAR it
# also has sim_end and sim_elapsed_s, the end and elapsed time of the simulation alone.

set -euo pipefail

RUN_DIR=$(cd -- "$1" && pwd)
# shellcheck source=/dev/null
source "$RUN_DIR/run.env"
cd -- "$RUN_DIR"
export NO_COLOR=1

timestamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }

START_S=$(date +%s)
START=$(timestamp)

write_result() {
    local exit_code=$1
    {
        echo "{"
        echo "  \"job_id\": \"${SLURM_JOB_ID:-}\","
        echo "  \"node\": \"$(hostname)\","
        echo "  \"start\": \"$START\","
        echo "  \"end\": \"$(timestamp)\","
        echo "  \"elapsed_s\": $(( $(date +%s) - START_S )),"
        if [[ -n ${SIM_END:-} ]]; then
            echo "  \"sim_end\": \"$SIM_END\","
            echo "  \"sim_elapsed_s\": $SIM_ELAPSED_S,"
        fi
        echo "  \"exit_code\": $exit_code"
        echo "}"
    } > "$RUN_DIR/result.json"
}
trap 'write_result $?' EXIT
# Slurm sends SIGTERM on scancel and when the time limit is reached. Exiting triggers the EXIT trap.
trap 'exit 143' TERM
trap 'exit 130' INT

read -ra JAVA_ARGS <<< "${JAVA_OPTS:-}"

if [[ ${ENGINE:-rust} == dsim || ${ENGINE:-rust} == qsim ]]; then
    # Java config, the mobsim is DSim or QSim
    if [[ $SCORING_MODE != enabled ]]; then
        echo "$ENGINE always scores, scoring=off is not supported." >&2
        exit 2
    fi
    CMD=("${JAVA:-java}" ${JAVA_ARGS[@]+"${JAVA_ARGS[@]}"} --add-exports java.base/jdk.internal.misc=ALL-UNNAMED
        -cp "$BIN" org.matsim.run.dsim.OpenBerlinDSimBenchmark --config "$CONFIG" --threads "$NUM_PARTS")
    if [[ -n ${SCORING_CONFIG:-} ]]; then
        CMD+=(--scoring-config "$SCORING_CONFIG")
    fi
    CMD+=(--output "$RUN_DIR/output"
        --config:controller.overwriteFiles=deleteDirectoryIfExists
        --config:controller.writeEventsInterval="$([[ $WRITE_EVENTS == file ]] && echo 1 || echo 0)")
    if [[ -n ${PLANS:-} ]]; then
        CMD+=(--config:plans.inputPlansFile="$PLANS")
    fi
    if [[ -n ${VEHICLES:-} ]]; then
        CMD+=(--config:vehicles.vehiclesFile="$VEHICLES")
    fi
    if [[ -n ${FACILITIES:-} ]]; then
        CMD+=(--config:facilities.inputFacilitiesFile="$FACILITIES")
    fi
    if [[ -n ${NETWORK:-} ]]; then
        CMD+=(--config:network.inputNetworkFile="$NETWORK" --config:dsim.partitioning=none)
    fi
    if [[ -n ${LAST_ITERATION:-} ]]; then
        CMD+=(--config:controller.lastIteration="$LAST_ITERATION")
    fi
    if [[ -n ${RUN_ID:-} ]]; then
        CMD+=(--config:controller.runId="$RUN_ID")
    fi
    if [[ $ENGINE == qsim ]]; then
        CMD+=(--config:controller.mobsim=qsim)
        if [[ -n ${QSIM_THREADS:-} ]]; then
            CMD+=(--config:qsim.numberOfThreads="$QSIM_THREADS")
        fi
    fi
    if [[ -n ${TRAFFIC_DYNAMICS:-} ]]; then
        CMD+=(--config:"$ENGINE".trafficDynamics="$TRAFFIC_DYNAMICS")
    fi
    if [[ -n ${LINK_DYNAMICS:-} ]]; then
        CMD+=(--config:"$ENGINE".linkDynamics="$LINK_DYNAMICS")
    fi
    if [[ -n ${SEED:-} ]]; then
        CMD+=(--config:global.randomSeed="$SEED")
    fi
else
    # Rust config
    CMD=("$BIN" --config "$CONFIG" "$NUM_PARTS"
        --set "output.output_dir=$RUN_DIR/output"
        --set "scoring.mode=$SCORING_MODE"
        --set "output.write_events=$WRITE_EVENTS"
        --set "controller.write_events_interval=1")
    if [[ -n ${NETWORK:-} ]]; then
        CMD+=(--set "network.path=$NETWORK" --set "partitioning.method=none")
    fi
    if [[ -n ${LAST_ITERATION:-} ]]; then
        CMD+=(--set "controller.last_iteration=$LAST_ITERATION")
    fi
    if [[ -n ${PLANS:-} ]]; then
        CMD+=(--set "population.path=$PLANS")
    fi
    if [[ -n ${TRAFFIC_DYNAMICS:-} ]]; then
        CMD+=(--set "qsim.traffic_dynamics=$TRAFFIC_DYNAMICS")
    fi
    if [[ -n ${LINK_DYNAMICS:-} ]]; then
        CMD+=(--set "qsim.link_dynamics=$LINK_DYNAMICS")
    fi
    if [[ -n ${SEED:-} ]]; then
        CMD+=(--set "computational_setup.random_seed=$SEED")
    fi
fi
CMD+=(${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"})

run() {
    if [[ -n ${SLURM_JOB_ID:-} ]]; then
        srun --nodes=1 --ntasks=1 --cpus-per-task="$SLURM_CPUS_PER_TASK" "$@"
    else
        "$@"
    fi
}

echo "Run directory: $RUN_DIR"
echo "Command: ${CMD[*]}"

run "${CMD[@]}"

if [[ ${ENGINE:-rust} == rust && -n ${TRIPS_JAR:-} ]]; then
    SIM_END=$(timestamp)
    SIM_ELAPSED_S=$(( $(date +%s) - START_S ))
    echo "Simulation ended at $SIM_END after $SIM_ELAPSED_S s, writing the trips."
    TRIPS_CMD=("${JAVA:-java}" ${JAVA_ARGS[@]+"${JAVA_ARGS[@]}"} -cp "$TRIPS_JAR"
        org.matsim.application.analysis.population.TripsAndLegsCsvWriter --run-directory "$RUN_DIR/output")
    echo "Command: ${TRIPS_CMD[*]}"
    run "${TRIPS_CMD[@]}"
    echo "Trips written at $(timestamp)."
fi
