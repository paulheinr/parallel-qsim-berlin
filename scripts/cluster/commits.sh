#!/bin/bash
#SBATCH --partition=cpu-genoa
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --exclusive
#SBATCH --time=01:00:00

# Compares berlin_iterations_v7 built with several commits of matsim-rust, optionally with a change of their sources.
# All runs run one after the other in a single job, i.e. on the same node, so that they can be compared without
# differences between nodes. The repetitions are interleaved (all cases once, then all again), so that a slow phase
# of the node does not hit only one build.
#
# On the cluster, in the repository root, on the login node:
#
#   scripts/cluster/commits.sh [name]        # name defaults to poll
#
# 1. builds berlin_iterations_v7 without hotpath for every entry of BUILDS: a copy of src/main/rust in
#    output/commits/<name>/build whose Cargo.toml takes matsim-rust from GitHub at that commit, or, for a build with a
#    change, from a changed copy of cargo's checkout of that commit (path dependency, in build/src/<build>). It has
#    its own target dir there (src/main/rust, its Cargo.toml and Cargo.lock and target/release are not touched). The
#    copy starts from the Cargo.lock of src/main/rust, so cargo changes only the entries of matsim-rust and macros.
#    The binaries are copied to output/commits/<name>/bin/<build>/, the target dir is deleted afterwards,
# 2. writes output/commits/<name>/runs/<case>_r<rep>/run.env, copied from the run of scaling-v4 with the same settings
#    (config, network, 10 iterations), with the binary of the case,
# 3. submits itself as one Slurm job (1 node, at most 1 h), which runs all cases with run-sim.sh.
#
# The target dir holds about 7k files and 3 GB (work has a limit of 250k inodes), a copy of matsim-rust about 400
# files. Each 1 % run takes about 1 min and writes its usual output (about 2 GB, 120 files, mostly plans and ITERS/).
# Logs: output/commits/<name>/slurm-<jobid>.log and runs/<case>_r<rep>/run.log. Fetch the results locally without
# plans, binaries and the build:
#
#   rsync -av --exclude='ITERS/' --exclude='*.binpb' --exclude='bin/' --exclude='build/' \
#     hlrn-genoa:scratch/iterations-rust/parallel-qsim-berlin/output/commits/<name> <local dir>
#
# Experiments: pr324 (the commits of PR #324, in the version of this script in commit 5210c0c) and poll (this one).

set -euo pipefail

# Builds: name (bin/<name>), commit of matsim-rust and optionally a change: a file of matsim-rust and a sed
# expression applied to it. A build with a change needs cargo's checkout of its commit in ~/.cargo/git/checkouts,
# i.e. the commit must have been built once without a change (all commits of pr324 were).
#
# poll: partitions poll for the messages of their neighbors for POLL_BEFORE_BLOCKING (50 us) and then block, so that
# the sender has to wake them up. The guess is that slightly longer steps then cause blocking and slow wake-ups that
# spread to the neighbors, which would explain why 3e477073 is slower than 99a27380 with scoring on (pr324) although
# its backpacking is cheaper, and why the RTR depends so much on the code layout. With 10 ms, partitions practically
# never block during the mobsim.
POLL_FILE=matsim_rust/src/simulation/messaging/sim_communication/local_communicator.rs
POLL_10MS='s/^const POLL_BEFORE_BLOCKING: Duration = .*;$/const POLL_BEFORE_BLOCKING: Duration = Duration::from_millis(10);/'
BUILDS=(
    "99a27380_poll10ms  99a27380e5b32f2bd94b31289e9addc2e63b0880  $POLL_FILE  $POLL_10MS"
    "3e477073_poll10ms  3e477073a2e3abcde25249f69dc1b711308b541f  $POLL_FILE  $POLL_10MS"
    "f2f49a27_poll10ms  f2f49a271f3bef29ed8cc96e9bf5a233fe64d0dd  $POLL_FILE  $POLL_10MS"
)
# Binaries that already exist: those of pr324 (unchanged, POLL_BEFORE_BLOCKING = 50 us).
declare -A BINARIES=(
    [99a27380]=output/commits/pr324/bin/99a27380/berlin_iterations_v7
    [3e477073]=output/commits/pr324/bin/3e477073/berlin_iterations_v7
    [f2f49a27]=output/commits/pr324/bin/f2f49a27/berlin_iterations_v7
)
# Cases: name, run of scaling-v4 whose run.env is used, binary (key in BINARIES or name of a build). In pr324, at 1 %,
# 96 partitions, scoring on: 99a27380 69.7k, 3e477073 58.3k, f2f49a27 (same code as 3e477073) 47.7k.
CASES=(
    "1pct_p096_on_99a27380            1pct_metis_p096_score-on_events-off_r1   99a27380"
    "1pct_p096_on_99a27380_poll10ms   1pct_metis_p096_score-on_events-off_r1   99a27380_poll10ms"
    "1pct_p096_on_3e477073            1pct_metis_p096_score-on_events-off_r1   3e477073"
    "1pct_p096_on_3e477073_poll10ms   1pct_metis_p096_score-on_events-off_r1   3e477073_poll10ms"
    "1pct_p096_on_f2f49a27            1pct_metis_p096_score-on_events-off_r1   f2f49a27"
    "1pct_p096_on_f2f49a27_poll10ms   1pct_metis_p096_score-on_events-off_r1   f2f49a27_poll10ms"
    "1pct_p096_off_99a27380           1pct_metis_p096_score-off_events-off_r1  99a27380"
    "1pct_p096_off_99a27380_poll10ms  1pct_metis_p096_score-off_events-off_r1  99a27380_poll10ms"
    "1pct_p192_on_f2f49a27            1pct_metis_p192_score-on_events-off_r1   f2f49a27"
    "1pct_p192_on_f2f49a27_poll10ms   1pct_metis_p192_score-on_events-off_r1   f2f49a27_poll10ms"
)
REPETITIONS=2
SOURCE=output/experiments/scaling-v4
MATSIM_RUST=https://github.com/matsim-vsp/matsim-rust

NAME=${1:-poll}
if [[ -n ${SLURM_JOB_ID:-} ]]; then
    cd -- "$SLURM_SUBMIT_DIR"
else
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
fi
OUT=$PWD/output/commits/$NAME

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
    mkdir -p "$OUT/build" "$OUT/bin" "$OUT/runs"
    cp scripts/cluster/commits.sh "$OUT/"
    cp -r src/main/rust/Cargo.toml src/main/rust/Cargo.lock src/main/rust/src "$OUT/build/"
    for build in "${BUILDS[@]}"; do
        read -r name commit file expr <<< "$build"
        echo "== building $name"
        mkdir -p "$OUT/bin/$name"
        if [[ -z ${file:-} ]]; then
            sed -i "s|^matsim-rust = .*|matsim-rust = { git = \"$MATSIM_RUST\", rev = \"$commit\" }|" \
                "$OUT/build/Cargo.toml"
        else
            checkout=$(find "$HOME/.cargo/git/checkouts" -mindepth 2 -maxdepth 2 -path '*/matsim-rust-*' \
                -name "${commit:0:7}" | head -n 1)
            [[ -n $checkout ]] || { echo "No cargo checkout of $commit, build it once without a change." >&2; exit 1; }
            src=$OUT/build/src/$name
            mkdir -p "$OUT/build/src"
            cp -r "$checkout" "$src"
            sed -i "$expr" "$src/$file"
            if diff "$checkout/$file" "$src/$file" > "$OUT/bin/$name/change.diff"; then
                echo "The change of $name does not change $file." >&2
                exit 1
            fi
            sed -i "s|^matsim-rust = .*|matsim-rust = { path = \"$src/matsim_rust\" }|" "$OUT/build/Cargo.toml"
        fi
        (cd "$OUT/build" && cargo build --release --target-dir target --bin berlin_iterations_v7)
        if [[ -z ${file:-} ]]; then
            grep -q "^source = \"git+$MATSIM_RUST?rev=$commit#$commit\"" "$OUT/build/Cargo.lock" \
                || { echo "Cargo.lock does not pin matsim-rust at $commit" >&2; exit 1; }
        elif grep -q "^source = \"git+$MATSIM_RUST" "$OUT/build/Cargo.lock"; then
            echo "Cargo.lock still takes matsim-rust from git for $name" >&2
            exit 1
        fi
        cp "$OUT/build/target/release/berlin_iterations_v7" "$OUT/build/Cargo.lock" "$OUT/bin/$name/"
        echo "$commit" > "$OUT/bin/$name/commit.txt"
        BINARIES[$name]=$OUT/bin/$name/berlin_iterations_v7
    done
    rm -rf "$OUT/build/target"
    {
        echo "built: $(date '+%Y-%m-%dT%H:%M:%S%z') without hotpath, from a copy of src/main/rust"
        echo "parallel-qsim-berlin: $(git rev-parse HEAD)$(git diff --quiet || echo ' (dirty)')"
        for key in $(printf '%s\n' "${!BINARIES[@]}" | sort); do
            echo "$key: $(sha256sum "${BINARIES[$key]}" | cut -c1-12) ${BINARIES[$key]}"
        done
    } > "$OUT/build_info.txt"

    for rep in $(seq 1 "$REPETITIONS"); do
        for case in "${CASES[@]}"; do
            read -r name run binary <<< "$case"
            [[ -n ${BINARIES[$binary]:-} ]] || { echo "Unknown binary $binary in case $name" >&2; exit 1; }
            run_dir=$OUT/runs/${name}_r$rep
            mkdir -p "$run_dir"
            {
                grep -v '^BIN=' "$SOURCE/runs/$run/run.env"
                echo "BIN=$(realpath "${BINARIES[$binary]}")"
            } > "$run_dir/run.env"
            echo "${name}_r$rep" >> "$OUT/cases.txt"
        done
    done
    cat "$OUT/build_info.txt"
    sbatch --job-name="$NAME" --output="$OUT/slurm-%j.log" scripts/cluster/commits.sh "$NAME"
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
