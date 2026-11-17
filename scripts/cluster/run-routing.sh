#!/bin/bash --login
#SBATCH --partition=cpu-genoa
#SBATCH --nodes=2
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=192
#SBATCH --exclusive

# Runs a rust simulation together with external pt routers in one Slurm job step. As with run-sim.sh, all parameters
# are read from <run_dir>/run.env, which scripts/cluster/cluster.py writes before submitting (settings e.g.
# cluster-routing.toml). Time limit, job name, log file and the number of nodes are set by cluster.py.
#
#   sbatch [--time=...] [--nodes=N --ntasks=N] scripts/cluster/run-routing.sh <run_dir>
#
# Every process gets a node of its own: the simulation the first node of the job, router i node i + 1, so a job with
# N nodes has N - 1 routers. One srun --multi-prog runs them as the tasks of one job step, with the commands in
# <run_dir>/tasks.conf:
# - All tasks start together. The simulation gets the addresses of the routers (--router-ip) and retries connecting
#   until they are ready (computational_setup.retry_time_seconds, default 600 s). A router opens its port only when
#   all its routing threads are ready.
# - If a task ends with an error, Slurm stops all tasks (--kill-on-bad-exit).
# - Otherwise the step ends with its last task: the simulation sends Shutdown to the routers as the very last thing
#   it does, and the routers end right after.
# - scancel and the time limit stop the whole step. result.json is written as in run-sim.sh.
# The output of all tasks goes into the Slurm log, each line prefixed with its task: 0: simulation, 1:, 2:, ... routers.
#
# run.env has the variables of the rust runs of run-sim.sh (BIN, CONFIG, NUM_PARTS, SCORING_MODE, WRITE_EVENTS and
# optionally NETWORK, LAST_ITERATION, TRAFFIC_DYNAMICS, LINK_DYNAMICS, SEED, PLANS, EXTRA_ARGS, TRIPS_JAR, JAVA,
# JAVA_OPTS) and
# - ROUTER_JAR, an executable jar (e.g. the jar of this repository, main class org.matsim.routing.RoutingServer), or
#   ROUTER_CLASSPATH and ROUTER_CLASS for another main class. A router takes --config, --threads, --port and
#   --output, opens its port only when it is ready and ends on Shutdown.
# - ROUTER_CONFIG, the MATSim config of the routers.
# - optionally ROUTER_THREADS (default: the CPUs of a node), ROUTER_MEMORY (maximum heap of a router, e.g. 400g),
#   ROUTER_DOMAIN (appended to the node names in the addresses, default ib.hlrn.de, i.e. InfiniBand on Lise; empty:
#   the node names alone) and HORIZON (--horizon: preplanning horizon of the pt trips in s).
#
# Without Slurm, start the router and the simulation yourself, see "Runs with external pt routers" in
# scripts/cluster/README.md. scripts/run-routing.sh (with the Makefile) is the old way and deprecated.

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

if [[ -z ${SLURM_JOB_ID:-} ]]; then
    fail "run-routing.sh runs only in a Slurm job. Without Slurm, start the router and the simulation yourself" \
        "(see scripts/cluster/README.md)."
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
read -ra NODES <<< "$(scontrol show hostnames "$SLURM_JOB_NODELIST" | tr '\n' ' ')"
if (( ${#NODES[@]} < 2 )); then
    fail "The job needs at least 2 nodes (simulation and one router), it has ${#NODES[@]}."
fi

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
if [[ -n ${HORIZON:-} ]]; then
    CMD+=(--horizon "$HORIZON")
fi
CMD+=(${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"})

# router i runs on node i + 1 and listens on port 50051
DOMAIN=${ROUTER_DOMAIN-ib.hlrn.de}
ADDRESSES=()
for node in "${NODES[@]:1}"; do
    ADDRESSES+=("http://$node${DOMAIN:+.$DOMAIN}:50051")
done
CMD+=(--router-ip "${ADDRESSES[@]}")

# One line per task: task number, program, arguments. Slurm splits the arguments at white space, without shell quoting,
# and replaces %t and %o in them, so arguments with white space, quotes, % or backslashes are refused.
TASKS=()
task() {
    local arg
    for arg in "${@:2}"; do
        if [[ -z $arg || $arg == *[[:space:]\'\"%\\]* ]]; then
            fail "Cannot write this argument into tasks.conf (empty, or with white space, quotes, % or \\): $arg"
        fi
    done
    TASKS+=("$*")
}
task 0 "${CMD[@]}"
for (( i = 0; i < ${#NODES[@]} - 1; i++ )); do
    ROUTER_CMD=("${JAVA:-java}")
    if [[ -n ${ROUTER_MEMORY:-} ]]; then
        ROUTER_CMD+=("-Xmx$ROUTER_MEMORY")
    fi
    ROUTER_CMD+=("${ROUTER_MAIN[@]}" --config "$ROUTER_CONFIG" --threads "${ROUTER_THREADS:-$SLURM_CPUS_PER_TASK}"
        --port 50051 --output "$RUN_DIR/routers/$i")
    task "$((i + 1))" "${ROUTER_CMD[@]}"
done
printf '%s\n' "${TASKS[@]}" > tasks.conf

echo "Run directory: $RUN_DIR"
echo "Tasks (tasks.conf):"
cat tasks.conf

# One task per node, task i on node i of the job. No --wait: the step ends with its last task, see above.
srun --nodes="${#NODES[@]}" --ntasks="${#NODES[@]}" --ntasks-per-node=1 --cpus-per-task="$SLURM_CPUS_PER_TASK" \
    --kill-on-bad-exit=1 --label --multi-prog tasks.conf

if [[ -n ${TRIPS_JAR:-} ]]; then
    SIM_END=$(timestamp)
    SIM_ELAPSED_S=$(( $(date +%s) - START_S ))
    echo "Simulation ended at $SIM_END after $SIM_ELAPSED_S s, writing the trips."
    read -ra JAVA_ARGS <<< "${JAVA_OPTS:-}"
    TRIPS_CMD=("${JAVA:-java}" ${JAVA_ARGS[@]+"${JAVA_ARGS[@]}"} -cp "$TRIPS_JAR"
        org.matsim.application.analysis.population.TripsAndLegsCsvWriter --run-directory "$RUN_DIR/output")
    echo "Command: ${TRIPS_CMD[*]}"
    srun --nodes=1 --ntasks=1 --cpus-per-task="$SLURM_CPUS_PER_TASK" "${TRIPS_CMD[@]}"
    echo "Trips written at $(timestamp)."
fi
