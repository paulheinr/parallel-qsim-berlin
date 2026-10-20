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
#   scripts/cluster/commits.sh [name]        # name defaults to revert
#
# 1. builds berlin_iterations_v7 without hotpath for every entry of BUILDS: a copy of src/main/rust in
#    output/commits/<name>/build whose Cargo.toml takes matsim-rust from GitHub at that commit, or from a copy of
#    cargo's checkout of that commit (path dependency, in build/src/<build>), which may be changed. It has its own
#    target dir there (src/main/rust, its Cargo.toml and Cargo.lock and target/release are not touched). The copy
#    starts from the Cargo.lock of src/main/rust, so cargo changes only the entries of matsim-rust and macros. The
#    binaries are copied to output/commits/<name>/bin/<build>/, the target dir is deleted afterwards,
# 2. writes output/commits/<name>/runs/<case>_r<rep>/run.env, copied from the run of scaling-v4 with the same settings
#    (config, network, 10 iterations), with the binary of the case,
# 3. submits itself as one Slurm job (1 node, at most TIME_LIMIT), which runs all cases with run-sim.sh.
#
# The target dir holds about 7k files and 3 GB (work has a limit of 250k inodes), a copy of matsim-rust about 400
# files. Each 1 % run takes about 1 min and writes its usual output (about 2 GB, 120 files, mostly plans and ITERS/;
# 3 %: about 2 min and 6 GB). Logs: output/commits/<name>/slurm-<jobid>.log and runs/<case>_r<rep>/run.log. Fetch the
# results locally without plans, binaries and the build:
#
#   rsync -av --exclude='ITERS/' --exclude='*.binpb' --exclude='bin/' --exclude='build/' \
#     hlrn-genoa:scratch/iterations-rust/parallel-qsim-berlin/output/commits/<name> <local dir>
#
# Experiments: pr324 (the commits of PR #324, this script in commit 5210c0c), poll (POLL_BEFORE_BLOCKING = 10 ms,
# commit 1b3be37) and revert (this one). Each output directory has a copy of the script it was made with.

set -euo pipefail

# Builds: name (bin/<name>), commit of matsim-rust and how matsim-rust is taken:
#   git                  git dependency at the commit (also when nothing is given)
#   copy                 path dependency on an unchanged copy of cargo's checkout of the commit
#   sed <file> <expr>    the same, with the sed expression applied to the file (relative to matsim-rust's root)
#   patch <file>         the same, with the patch (relative to this repository's root) applied with patch -p1
# All but git need cargo's checkout of the commit in ~/.cargo/git/checkouts, i.e. the commit must have been built
# once as a git dependency (all commits of pr324 and eec3c5f were).
#
# revert: in pr324 and poll, 3e477073 (smaller backpacks and vehicle occupants) made the mobsim slower with scoring on
# (1 %, 96 partitions: 99a27380 69.7k/71.7k, 3e477073 58.3k/56.1k), also when partitions never block (poll). The
# final test takes eec3c5f (= scaling-v4, PR #324 merged) and takes back all of 3e477073 (patches/revert-3e477073.patch
# is `git diff 3e477073 99a27380 -- matsim_rust/src`). eec3c5f_copy is built the same way without the patch, so that
# the way of building does not matter.
BUILDS=(
    "eec3c5f_copy    eec3c5ff9e3899e91dd5c234a197920c46210950  copy"
    "eec3c5f_revert  eec3c5ff9e3899e91dd5c234a197920c46210950  patch  scripts/cluster/patches/revert-3e477073.patch"
)
# Binaries that already exist: those of pr324 (git dependencies). f2f49a27 has the same tree as eec3c5f.
declare -A BINARIES=(
    [f91a7b29]=output/commits/pr324/bin/f91a7b29/berlin_iterations_v7
    [99a27380]=output/commits/pr324/bin/99a27380/berlin_iterations_v7
    [f2f49a27]=output/commits/pr324/bin/f2f49a27/berlin_iterations_v7
)
# Cases: name, run of scaling-v4 whose run.env is used, binary (key in BINARIES or name of a build) and optionally the
# number of repetitions (default REPETITIONS). Runs of 3e477073 and later spread by up to 20 %, so the main case has
# four repetitions.
CASES=(
    "1pct_p096_on_f91a7b29         1pct_metis_p096_score-on_events-off_r1  f91a7b29        4"
    "1pct_p096_on_99a27380         1pct_metis_p096_score-on_events-off_r1  99a27380        4"
    "1pct_p096_on_f2f49a27         1pct_metis_p096_score-on_events-off_r1  f2f49a27        4"
    "1pct_p096_on_eec3c5f_copy     1pct_metis_p096_score-on_events-off_r1  eec3c5f_copy    4"
    "1pct_p096_on_eec3c5f_revert   1pct_metis_p096_score-on_events-off_r1  eec3c5f_revert  4"
    "3pct_p096_on_f2f49a27         3pct_metis_p096_score-on_events-off_r1  f2f49a27"
    "3pct_p096_on_eec3c5f_revert   3pct_metis_p096_score-on_events-off_r1  eec3c5f_revert"
    "1pct_p192_on_f2f49a27         1pct_metis_p192_score-on_events-off_r1  f2f49a27"
    "1pct_p192_on_eec3c5f_revert   1pct_metis_p192_score-on_events-off_r1  eec3c5f_revert"
)
REPETITIONS=2
TIME_LIMIT=01:30:00
SOURCE=output/experiments/scaling-v4
MATSIM_RUST=https://github.com/matsim-vsp/matsim-rust

NAME=${1:-revert}
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
    for build in "${BUILDS[@]}"; do
        read -r name commit mode arg rest <<< "$build"
        if [[ $mode == patch ]]; then
            [[ -f $arg ]] || { echo "Patch of $name not found: $arg" >&2; exit 1; }
        fi
    done

    # shellcheck source=/dev/null
    source "$HOME/.cargo/env"
    mkdir -p "$OUT/build" "$OUT/bin" "$OUT/runs"
    cp scripts/cluster/commits.sh "$OUT/"
    cp -r src/main/rust/Cargo.toml src/main/rust/Cargo.lock src/main/rust/src "$OUT/build/"
    for build in "${BUILDS[@]}"; do
        read -r name commit mode arg rest <<< "$build"
        mode=${mode:-git}
        echo "== building $name ($mode)"
        mkdir -p "$OUT/bin/$name"
        echo "$build" > "$OUT/bin/$name/build.txt"
        if [[ $mode == git ]]; then
            sed -i "s|^matsim-rust = .*|matsim-rust = { git = \"$MATSIM_RUST\", rev = \"$commit\" }|" \
                "$OUT/build/Cargo.toml"
        else
            checkout=$(find "$HOME/.cargo/git/checkouts" -mindepth 2 -maxdepth 2 -path '*/matsim-rust-*' \
                -name "${commit:0:7}" | head -n 1)
            [[ -n $checkout ]] || { echo "No cargo checkout of $commit, build it once with git." >&2; exit 1; }
            src=$OUT/build/src/$name
            mkdir -p "$OUT/build/src"
            cp -r "$checkout" "$src"
            case $mode in
                copy) ;;
                sed) sed -i "$rest" "$src/$arg" ;;
                patch) patch -d "$src" -p1 --forward --batch < "$arg" ;;
                *) echo "Unknown mode $mode of $name" >&2; exit 1 ;;
            esac
            if [[ $mode != copy ]]; then
                if diff -r -x .git "$checkout" "$src" > "$OUT/bin/$name/change.diff"; then
                    echo "The change of $name changes nothing." >&2
                    exit 1
                fi
            fi
            sed -i "s|^matsim-rust = .*|matsim-rust = { path = \"$src/matsim_rust\" }|" "$OUT/build/Cargo.toml"
        fi
        (cd "$OUT/build" && cargo build --release --target-dir target --bin berlin_iterations_v7)
        if [[ $mode == git ]]; then
            grep -q "^source = \"git+$MATSIM_RUST?rev=$commit#$commit\"" "$OUT/build/Cargo.lock" \
                || { echo "Cargo.lock does not pin matsim-rust at $commit" >&2; exit 1; }
        elif grep -q "^source = \"git+$MATSIM_RUST" "$OUT/build/Cargo.lock"; then
            echo "Cargo.lock still takes matsim-rust from git for $name" >&2
            exit 1
        fi
        cp "$OUT/build/target/release/berlin_iterations_v7" "$OUT/build/Cargo.lock" "$OUT/bin/$name/"
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

    max_reps=$REPETITIONS
    for case in "${CASES[@]}"; do
        read -r name run binary reps <<< "$case"
        (( ${reps:-$REPETITIONS} > max_reps )) && max_reps=$reps
    done
    for rep in $(seq 1 "$max_reps"); do
        for case in "${CASES[@]}"; do
            read -r name run binary reps <<< "$case"
            (( rep <= ${reps:-$REPETITIONS} )) || continue
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
    echo "$(wc -l < "$OUT/cases.txt") runs, time limit $TIME_LIMIT"
    sbatch --job-name="$NAME" --time="$TIME_LIMIT" --output="$OUT/slurm-%j.log" scripts/cluster/commits.sh "$NAME"
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
