#!/bin/bash --login
# Runs a rust simulation together with external pt routers as a heterogeneous Slurm job: component 0 is the simulation
# (one node), component 1 the routers (one router per node). As with run-sim.sh, all parameters are read from
# <run_dir>/run.env, which scripts/cluster/cluster.py writes before submitting (settings e.g. cluster-routing.toml).
# cluster.py also sets the components, time limit, job name and log file ([slurm] routers = R):
#
#   sbatch [job options] --partition=P --time=T --nodes=1 --ntasks=1 \
#       : --partition=P --time=T --nodes=R --ntasks=R scripts/cluster/run-routing.sh <run_dir>
#
# One srun starts both components as one heterogeneous job step:
# - All tasks start together. The simulation gets the addresses of the routers (--router-ip) and retries connecting
#   until they are ready (computational_setup.retry_time_seconds, default 600 s). A router opens its port only when
#   all its routing threads are ready.
# - If a task ends with an error, Slurm stops all tasks (--kill-on-bad-exit).
# - Otherwise the step ends with its last task: the simulation sends Shutdown to the routers as the very last thing
#   it does, and the routers end right after.
# - scancel and the time limit stop the whole step. result.json is written as in run-sim.sh.
# The output of all tasks goes into the Slurm log, each line prefixed with its task: 0: simulation, 1:, 2:, ... routers.
# Each router writes its output to <run_dir>/routers/<node>/.
#
# run.env has the variables of the rust runs of run-sim.sh (BIN, CONFIG, NUM_PARTS, SCORING_MODE, WRITE_EVENTS and
# optionally NETWORK, LAST_ITERATION, TRAFFIC_DYNAMICS, LINK_DYNAMICS, SEED, PLANS, EXTRA_ARGS, TRIPS_JAR, JAVA,
# JAVA_OPTS) and
# - ROUTER_JAR, an executable jar (e.g. the jar of this repository, main class org.matsim.routing.RoutingServer), or
#   ROUTER_CLASSPATH and ROUTER_CLASS for another main class. A router takes --config, --threads, --port and
#   --output, opens its port only when it is ready and ends on Shutdown.
# - ROUTER_CONFIG, the MATSim config of the routers.
# - optionally ROUTER_THREADS (default: the CPUs of a router node), ROUTER_MEMORY (maximum heap of a router, e.g.
#   400g), ROUTER_DOMAIN (appended to the node names in the addresses, default ib.hlrn.de, i.e. InfiniBand on Lise;
#   empty: the node names alone), HORIZON (--horizon: preplanning horizon of the pt trips in s) and WORKER_THREADS
#   (computational_setup.adapter_worker_threads: async worker threads of the routing adapter of the simulation).
#
# Without Slurm, start the router and the simulation yourself, see "Runs with external pt routers" in
# scripts/cluster/README.md.

set -euo pipefail

RUN_DIR=$(cd -- "$1" && pwd)
# shellcheck source=/dev/null
source "$RUN_DIR/run.env"
cd -- "$RUN_DIR"
export NO_COLOR=1

timestamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }

START_S=$(date +%s)
START=$(timestamp)

# the same fields as in run-sim.sh, collect reads them
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

fail() {
    echo "$*" >&2
    exit 2
}

if [[ ${SLURM_HET_SIZE:-} != 2 ]]; then
    fail "run-routing.sh runs only in a heterogeneous Slurm job with two components (simulation and routers), see" \
        "its header. Without Slurm, start the router and the simulation yourself (see scripts/cluster/README.md)."
fi
if [[ ${ENGINE:-rust} != rust ]]; then
    fail "run-routing.sh runs only rust simulations, not ENGINE=$ENGINE."
fi
if [[ -n ${ROUTER_JAR:-} ]]; then
    ROUTER_MAIN=(-jar "$ROUTER_JAR")
elif [[ -n ${ROUTER_CLASSPATH:-} && -n ${ROUTER_CLASS:-} ]]; then
    ROUTER_MAIN=(-cp "$ROUTER_CLASSPATH" "$ROUTER_CLASS")
else
    fail "Set ROUTER_JAR, or ROUTER_CLASSPATH and ROUTER_CLASS."
fi
if [[ -z ${ROUTER_CONFIG:-} ]]; then
    fail "Set ROUTER_CONFIG, the MATSim config of the routers."
fi
read -ra ROUTER_NODES <<< "$(scontrol show hostnames "$SLURM_JOB_NODELIST_HET_GROUP_1" | tr '\n' ' ')"
# CPUs of a node of each component, e.g. "192" or "192(x2)"; the nodes are exclusive
SIM_CPUS=${SLURM_JOB_CPUS_PER_NODE_HET_GROUP_0%%(*}
ROUTER_CPUS=${SLURM_JOB_CPUS_PER_NODE_HET_GROUP_1%%(*}

# the simulation, as the rust runs of run-sim.sh
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
if [[ -n ${WORKER_THREADS:-} ]]; then
    CMD+=(--set "computational_setup.adapter_worker_threads=$WORKER_THREADS")
fi
if [[ -n ${HORIZON:-} ]]; then
    CMD+=(--horizon "$HORIZON")
fi
CMD+=(${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"})

# one router per node of component 1, listening on port 50051
DOMAIN=${ROUTER_DOMAIN-ib.hlrn.de}
ADDRESSES=()
for node in "${ROUTER_NODES[@]}"; do
    ADDRESSES+=("http://$node${DOMAIN:+.$DOMAIN}:50051")
done
CMD+=(--router-ip "${ADDRESSES[@]}")

ROUTER_CMD=("${JAVA:-java}")
if [[ -n ${ROUTER_MEMORY:-} ]]; then
    ROUTER_CMD+=("-Xmx$ROUTER_MEMORY")
fi
ROUTER_CMD+=("${ROUTER_MAIN[@]}" --config "$ROUTER_CONFIG" --threads "${ROUTER_THREADS:-$ROUTER_CPUS}" --port 50051)

echo "Run directory: $RUN_DIR"
echo "Simulation on $SLURM_JOB_NODELIST_HET_GROUP_0 ($SIM_CPUS CPUs): ${CMD[*]}"
echo "Routers on ${ROUTER_NODES[*]} ($ROUTER_CPUS CPUs each): ${ROUTER_CMD[*]} --output $RUN_DIR/routers/<node>"

# One heterogeneous step: component 0 the simulation, component 1 one router per node, each writing to
# routers/<node>. No --wait: the step ends with its last task, see above.
srun --kill-on-bad-exit=1 --label --ntasks=1 --cpus-per-task="$SIM_CPUS" "${CMD[@]}" \
    : --kill-on-bad-exit=1 --label --ntasks="${#ROUTER_NODES[@]}" --ntasks-per-node=1 --cpus-per-task="$ROUTER_CPUS" \
    bash -c 'exec "$@" --output "$0/routers/$(hostname -s)"' "$RUN_DIR" "${ROUTER_CMD[@]}"

if [[ -n ${TRIPS_JAR:-} ]]; then
    SIM_END=$(timestamp)
    SIM_ELAPSED_S=$(( $(date +%s) - START_S ))
    echo "Simulation ended at $SIM_END after $SIM_ELAPSED_S s, writing the trips."
    read -ra JAVA_ARGS <<< "${JAVA_OPTS:-}"
    TRIPS_CMD=("${JAVA:-java}" ${JAVA_ARGS[@]+"${JAVA_ARGS[@]}"} -cp "$TRIPS_JAR"
        org.matsim.application.analysis.population.TripsAndLegsCsvWriter --run-directory "$RUN_DIR/output")
    echo "Command: ${TRIPS_CMD[*]}"
    srun --het-group=0 --ntasks=1 --cpus-per-task="$SIM_CPUS" "${TRIPS_CMD[@]}"
    echo "Trips written at $(timestamp)."
fi
