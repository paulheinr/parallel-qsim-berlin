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
# optionally NETWORK (pre-partitioned network), LAST_ITERATION (0-based, inclusive) and EXTRA_ARGS (bash array of
# additional arguments).
#
# With ENGINE=dsim (set in cluster-dsim.toml), BIN is the matsim-berlin jar and the run is done with DSim. This also needs
# PLANS, VEHICLES and FACILITIES, and optionally JAVA and JAVA_OPTS.
#
# At the end, result.json is written into the run directory (also on failure, scancel and time limit).

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
    cat > "$RUN_DIR/result.json" <<EOF
{
  "job_id": "${SLURM_JOB_ID:-}",
  "node": "$(hostname)",
  "start": "$START",
  "end": "$(timestamp)",
  "elapsed_s": $(( $(date +%s) - START_S )),
  "exit_code": $exit_code
}
EOF
}
trap 'write_result $?' EXIT
# Slurm sends SIGTERM on scancel and when the time limit is reached. Exiting triggers the EXIT trap.
trap 'exit 143' TERM
trap 'exit 130' INT

if [[ ${ENGINE:-rust} == dsim ]]; then
    if [[ $SCORING_MODE != enabled ]]; then
        echo "DSim always scores, scoring=off is not supported." >&2
        exit 2
    fi
    read -ra JAVA_ARGS <<< "${JAVA_OPTS:-}"
    CMD=("${JAVA:-java}" ${JAVA_ARGS[@]+"${JAVA_ARGS[@]}"} --add-exports java.base/jdk.internal.misc=ALL-UNNAMED
        -cp "$BIN" org.matsim.run.dsim.OpenBerlinDSimBenchmark --config "$CONFIG" --threads "$NUM_PARTS"
        --output "$RUN_DIR/output"
        --config:controller.overwriteFiles=deleteDirectoryIfExists
        --config:controller.writeEventsInterval="$([[ $WRITE_EVENTS == file ]] && echo 1 || echo 0)"
        --config:plans.inputPlansFile="$PLANS"
        --config:vehicles.vehiclesFile="$VEHICLES"
        --config:facilities.inputFacilitiesFile="$FACILITIES")
    if [[ -n ${NETWORK:-} ]]; then
        CMD+=(--config:network.inputNetworkFile="$NETWORK" --config:dsim.partitioning=none)
    fi
    if [[ -n ${LAST_ITERATION:-} ]]; then
        CMD+=(--config:controller.lastIteration="$LAST_ITERATION")
    fi
else
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
fi
CMD+=(${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"})

echo "Run directory: $RUN_DIR"
echo "Command: ${CMD[*]}"

if [[ -n ${SLURM_JOB_ID:-} ]]; then
    srun --nodes=1 --ntasks=1 --cpus-per-task="$SLURM_CPUS_PER_TASK" "${CMD[@]}"
else
    "${CMD[@]}"
fi
