#!/bin/bash --login
#SBATCH --partition=cpu-genoa
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --exclusive
#SBATCH --time=02:00:00

# Job of the raptor benchmark (step B6 of the design doc on exogenous pt delays) on Lise: run.sh on one exclusive Genoa
# node, all runs one after the other, so that they can be compared without differences between nodes. The bundle comes
# from bundle.sh on the Mac and is copied to the cluster. On the login node, in the repository root:
#
#   sbatch --job-name=raptor-<name> --output=output/benchmark/raptor/<name>/slurm-%j.log \
#     output/benchmark/raptor/<name>/bundle/slurm.sh output/benchmark/raptor/<name>/bundle output/benchmark/raptor/<name>
#
# More arguments are passed to run.sh, and so to RaptorBenchmark. The login shell (first line) puts java of miniforge on
# the PATH. Lise sets SBATCH_EXPORT=none, so the environment of run.sh has to be passed with --export, e.g. for one
# profiled fork of three variants (with a shorter time limit):
#
#   sbatch --time=00:45:00 --export='FORKS=1,JFR=1,VARIANTS=base/schedule branch/option branch/versioned' ...
#
# Fetch the results without the bundle:
#
#   rsync -av --exclude=bundle/ hlrn-genoa:scratch/iterations-rust/parallel-qsim-berlin/output/benchmark/raptor/<name>/ \
#     output/benchmark/raptor/<name>/

set -euo pipefail

cd -- "$SLURM_SUBMIT_DIR"
echo "Node $(hostname), job $SLURM_JOB_ID, $(date '+%Y-%m-%dT%H:%M:%S%z')"
BUNDLE=$1
OUT=$2
shift 2
"$BUNDLE/run.sh" "$BUNDLE" "$OUT" "$@"
