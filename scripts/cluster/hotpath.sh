#!/bin/bash
#SBATCH --partition=cpu-genoa
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --exclusive
#SBATCH --time=01:00:00

# Profiles a few runs of berlin_iterations_v7 with hotpath (https://hotpath.rs): wall time and number of calls of the
# functions that matsim-rust marks with #[hotpath::measure] (simulation step, engines, message broker, backpacking,
# phases of the controller), the channels between the partitions and the CPU usage of the threads. All runs run one
# after the other in a single job, i.e. on the same node, so that they can be compared without differences between
# nodes.
#
# On the cluster, in the repository root, on the login node:
#
#   scripts/cluster/hotpath.sh [name]        # name defaults to hotpath-v4
#
# 1. builds berlin_iterations_v7 with --features hotpath into src/main/rust/target/hotpath (target/release, which
#    cluster.py submits, is not touched) and copies it to output/hotpath/<name>/bin,
# 2. writes output/hotpath/<name>/runs/<case>/run.env, copied from the run of scaling-v4 with the same settings (config,
#    network, 10 iterations), with the binary of the case,
# 3. submits itself as one Slurm job (1 node, at most 1 h), which runs all cases with run-sim.sh.
#
# Caution: with --features hotpath, matsim-rust also wraps the channels between the partitions (hotpath::channel! in
# local_communicator.rs). Every message then goes through hotpath, and its collector thread is busy 90 % of the time.
# This makes runs with many partitions much slower (hotpath-v4b: RTR 2.3x lower at 96 and 3x lower at 192
# partitions), and message_broker::send_recv mostly measures the instrumentation. The times of the other functions
# are still useful.
#
# Every hotpath run writes hotpath.json (the report as JSON) into its run directory. Each run also writes its usual
# output (instrument/*.csv for the RTR, plans, ITERS/; about 6 GB at 3 %). Logs: output/hotpath/<name>/slurm-<jobid>.log
# and runs/<case>/run.log. Fetch the results locally without plans and binaries:
#
#   rsync -av --exclude='ITERS/' --exclude='*.binpb' --exclude='bin/' \
#     hlrn-genoa:scratch/iterations-rust/parallel-qsim-berlin/output/hotpath/<name> <local dir>

set -euo pipefail

# Cases: name, run of scaling-v4 whose run.env is used, binary (hotpath: built here with hotpath; v4, v3: the
# unchanged binaries of scaling-v4 and scaling-v3, without hotpath). With scoring on and 1 % at 96 partitions,
# scaling-v4 was much slower than scaling-v3 (40.9k instead of 66.2k), the plain runs check this on one node. Together
# with 1pct_p096_on they also show the overhead of hotpath.
CASES=(
    "1pct_p096_on_v4      1pct_metis_p096_score-on_events-off_r1   v4"
    "1pct_p096_on_v3      1pct_metis_p096_score-on_events-off_r1   v3"
    "1pct_p032_on         1pct_metis_p032_score-on_events-off_r1   hotpath"
    "1pct_p096_on         1pct_metis_p096_score-on_events-off_r1   hotpath"
    "1pct_p096_off        1pct_metis_p096_score-off_events-off_r1  hotpath"
    "1pct_p192_on         1pct_metis_p192_score-on_events-off_r1   hotpath"
    "3pct_p032_on         3pct_metis_p032_score-on_events-off_r1   hotpath"
    "3pct_p096_on         3pct_metis_p096_score-on_events-off_r1   hotpath"
    "3pct_p096_off        3pct_metis_p096_score-off_events-off_r1  hotpath"
    "3pct_p192_on         3pct_metis_p192_score-on_events-off_r1   hotpath"
)
SOURCE=output/experiments/scaling-v4
declare -A BINARIES=(
    [v4]=output/experiments/scaling-v4/bin/2e6d98a7a46b/berlin_iterations_v7
    [v3]=output/experiments/scaling-v3/bin/9374a1fbd8b4/berlin_iterations_v7
)

NAME=${1:-hotpath-v4}
if [[ -n ${SLURM_JOB_ID:-} ]]; then
    cd -- "$SLURM_SUBMIT_DIR"
else
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
fi
OUT=$PWD/output/hotpath/$NAME

if [[ -z ${SLURM_JOB_ID:-} ]]; then
    # login node: build, write the run directories, submit
    if [[ -e $OUT ]]; then
        echo "$OUT exists already, choose another name." >&2
        exit 1
    fi
    for key in "${!BINARIES[@]}"; do
        [[ -x ${BINARIES[$key]} ]] || { echo "Binary $key not found: ${BINARIES[$key]}" >&2; exit 1; }
    done

    # shellcheck source=/dev/null
    source "$HOME/.cargo/env"
    (cd src/main/rust && cargo build --release --locked --features hotpath --target-dir target/hotpath \
        --bin berlin_iterations_v7)
    mkdir -p "$OUT/bin" "$OUT/runs"
    cp src/main/rust/target/hotpath/release/berlin_iterations_v7 "$OUT/bin/berlin_iterations_v7-hotpath"
    BINARIES[hotpath]=$OUT/bin/berlin_iterations_v7-hotpath
    {
        echo "built: $(date '+%Y-%m-%dT%H:%M:%S%z') with --features hotpath"
        echo "parallel-qsim-berlin: $(git rev-parse HEAD)$(git diff --quiet || echo ' (dirty)')"
        echo "matsim-rust: $(grep -A2 '^name = "matsim-rust"' src/main/rust/Cargo.lock | grep '^source' || true)"
        for key in "${!BINARIES[@]}"; do
            echo "$key: $(sha256sum "${BINARIES[$key]}" | cut -c1-12) ${BINARIES[$key]}"
        done
    } > "$OUT/build_info.txt"

    for case in "${CASES[@]}"; do
        read -r name run binary <<< "$case"
        run_dir=$OUT/runs/$name
        mkdir -p "$run_dir"
        {
            grep -v '^BIN=' "$SOURCE/runs/$run/run.env"
            echo "BIN=$(realpath "${BINARIES[$binary]}")"
            if [[ $binary == hotpath ]]; then
                echo "export HOTPATH_OUTPUT_FORMAT=json-pretty"
                echo "export HOTPATH_OUTPUT_PATH=$run_dir/hotpath.json"
                echo "export HOTPATH_METRICS_SERVER_OFF=1"  # no HTTP server on the compute node
                echo "export HOTPATH_DISABLE_HINTS=1"
                echo "export HOTPATH_LIMIT=0"  # all functions and threads, not only the top 15 and 5
            fi
        } > "$run_dir/run.env"
        echo "$name" >> "$OUT/cases.txt"
    done
    cat "$OUT/build_info.txt"
    sbatch --job-name="$NAME" --output="$OUT/slurm-%j.log" scripts/cluster/hotpath.sh "$NAME"
    exit 0
fi

# Slurm job: run all cases one after the other
echo "Node $(hostname), job $SLURM_JOB_ID, $(date '+%Y-%m-%dT%H:%M:%S%z')"
# Read the cases first and give run-sim.sh no stdin: srun forwards stdin to the run, which would swallow the list.
mapfile -t names < "$OUT/cases.txt"
for name in "${names[@]}"; do
    echo "== $name ($(date '+%H:%M:%S'))"
    if scripts/cluster/run-sim.sh "$OUT/runs/$name" > "$OUT/runs/$name/run.log" 2>&1 < /dev/null; then
        echo "   done"
    else
        echo "   failed with exit code $?, see runs/$name/run.log"
    fi
done
echo "Finished $(date '+%Y-%m-%dT%H:%M:%S%z')"
