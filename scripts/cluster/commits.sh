#!/bin/bash
#SBATCH --partition=cpu-genoa
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --exclusive
#SBATCH --time=01:00:00

# Compares berlin_iterations_v7 built with several commits of matsim-rust. All runs run one after the other in a
# single job, i.e. on the same node, so that they can be compared without differences between nodes. The repetitions
# are interleaved (all cases once, then all again), so that a slow phase of the node does not hit only one commit.
#
# On the cluster, in the repository root, on the login node:
#
#   scripts/cluster/commits.sh [name]        # name defaults to pr324
#
# 1. builds berlin_iterations_v7 without hotpath for every commit in COMMITS: a copy of src/main/rust in
#    output/commits/<name>/build whose Cargo.toml takes matsim-rust from GitHub at that commit, with its own target
#    dir there (src/main/rust, its Cargo.toml and Cargo.lock and target/release are not touched). The copy starts
#    from the Cargo.lock of src/main/rust, so cargo changes only the entry of matsim-rust. The binaries are copied to
#    output/commits/<name>/bin/<commit>/,
# 2. writes output/commits/<name>/runs/<case>_r<rep>/run.env, copied from the run of scaling-v4 with the same settings
#    (config, network, 10 iterations), with the binary of the case,
# 3. submits itself as one Slurm job (1 node, at most 1 h), which runs all cases with run-sim.sh.
#
# The target dir holds about 7k files and 3 GB (work has a limit of 250k inodes). It is not needed after the builds.
# Each 1 % run takes about 1 min and writes its usual output (about 2 GB, 120 files, mostly plans and ITERS/). Logs:
# output/commits/<name>/slurm-<jobid>.log and runs/<case>_r<rep>/run.log. Fetch the results locally without plans,
# binaries and the build:
#
#   rsync -av --exclude='ITERS/' --exclude='*.binpb' --exclude='bin/' --exclude='build/' \
#     hlrn-genoa:scratch/iterations-rust/parallel-qsim-berlin/output/commits/<name> <local dir>

set -euo pipefail

# Commits of matsim-rust to build (bin/<first 8 characters>). PR #324 (merged as eec3c5f, same tree as f2f49a27)
# made the mobsim slower with scoring on at many partitions. Its parent is 47cb835c (#323 merged), whose parent is
# f91a7b2 (scaling-v3). The commits of #324 in between that are not listed change only tests, docs or add
# #[hotpath::measure], which is a no-op without the feature.
COMMITS=(
    f91a7b2974ab7b980598b576d60e2188bf088ed0  # scaling-v3
    47cb835c66a79f91abfdea4ee5f7b28fe29ee56a  # #323 merged: spin-then-park barrier
    2c4135cf8aa9d33f3b954d06e0149dc7bde48880  # subscribe backpacking only to the event types it needs
    99a27380e5b32f2bd94b31289e9addc2e63b0880  # keep the ids when finishing experienced plans
    3e477073a2e3abcde25249f69dc1b711308b541f  # smaller backpacks and vehicle occupants
    f2f49a271f3bef29ed8cc96e9bf5a233fe64d0dd  # typed event methods in backpack and partial plans (= eec3c5f)
)
# Binaries that already exist: those of scaling-v3 (f91a7b2) and scaling-v4 (eec3c5f). Rebuilt here as f91a7b29 and
# f2f49a27, they show whether a build in this way runs as fast as the original one.
declare -A BINARIES=(
    [v3]=output/experiments/scaling-v3/bin/9374a1fbd8b4/berlin_iterations_v7
    [v4]=output/experiments/scaling-v4/bin/2e6d98a7a46b/berlin_iterations_v7
)
# Cases: name, run of scaling-v4 whose run.env is used, binary (key in BINARIES or the first 8 characters of a
# commit). With scoring on and 1 % at 96 partitions, scaling-v4 was much slower than scaling-v3 (40.9k instead of
# 66.2k; 48.9k and 70.9k on the same node in hotpath-v4b), without scoring it was not.
CASES=(
    "1pct_p096_on_f91a7b29   1pct_metis_p096_score-on_events-off_r1   f91a7b29"
    "1pct_p096_on_47cb835c   1pct_metis_p096_score-on_events-off_r1   47cb835c"
    "1pct_p096_on_2c4135cf   1pct_metis_p096_score-on_events-off_r1   2c4135cf"
    "1pct_p096_on_99a27380   1pct_metis_p096_score-on_events-off_r1   99a27380"
    "1pct_p096_on_3e477073   1pct_metis_p096_score-on_events-off_r1   3e477073"
    "1pct_p096_on_f2f49a27   1pct_metis_p096_score-on_events-off_r1   f2f49a27"
    "1pct_p096_on_v3         1pct_metis_p096_score-on_events-off_r1   v3"
    "1pct_p096_on_v4         1pct_metis_p096_score-on_events-off_r1   v4"
    "1pct_p096_off_v3        1pct_metis_p096_score-off_events-off_r1  v3"
    "1pct_p096_off_v4        1pct_metis_p096_score-off_events-off_r1  v4"
)
REPETITIONS=2
SOURCE=output/experiments/scaling-v4
MATSIM_RUST=https://github.com/matsim-vsp/matsim-rust

NAME=${1:-pr324}
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
    cp -r src/main/rust/Cargo.toml src/main/rust/Cargo.lock src/main/rust/src "$OUT/build/"
    for commit in "${COMMITS[@]}"; do
        short=${commit:0:8}
        echo "== building $short"
        sed -i "s|^matsim-rust = .*|matsim-rust = { git = \"$MATSIM_RUST\", rev = \"$commit\" }|" "$OUT/build/Cargo.toml"
        (cd "$OUT/build" && cargo build --release --target-dir target --bin berlin_iterations_v7)
        grep -q "^source = \"git+$MATSIM_RUST?rev=$commit#$commit\"" "$OUT/build/Cargo.lock" \
            || { echo "Cargo.lock does not pin matsim-rust at $commit" >&2; exit 1; }
        mkdir -p "$OUT/bin/$short"
        cp "$OUT/build/target/release/berlin_iterations_v7" "$OUT/bin/$short/"
        cp "$OUT/build/Cargo.lock" "$OUT/bin/$short/"
        BINARIES[$short]=$OUT/bin/$short/berlin_iterations_v7
    done
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
