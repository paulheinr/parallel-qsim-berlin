#!/bin/bash --login
#SBATCH --partition=cpu-genoa
#SBATCH --cpus-per-task=192
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:30:00
#SBATCH --job-name=berlin-iterations-v7
#SBATCH --output=output/logs/berlin_iterations_v7_%j.log
#SBATCH --mail-user=heinrich@vsp.tu-berlin.de
#SBATCH --mail-type=BEGIN,END,FAIL

set -euo pipefail

# Submit from the repository root (threads, percentage):
# mkdir -p output/logs
# sbatch scripts/run-berlin-iterations-v7.sh 16 10
# sbatch --time=00:10:00 scripts/run-berlin-iterations-v7.sh 16 1

THREADS=$1
PCT=$2

cd -- "$SLURM_SUBMIT_DIR"
CONFIG="$PWD/input/v7.1/berlin-v7.1.${PCT}pct.config.yml"
OUTPUT_DIR="$PWD/output/v7.1/${PCT}pct/iterations_${THREADS}threads_${SLURM_JOB_ID}"
export NO_COLOR=1

exec srun --nodes=1 --ntasks=1 --cpus-per-task=192 \
    ./src/main/rust/target/release/berlin_iterations_v7 \
    --config "$CONFIG" "$THREADS" \
    --set "output.output_dir=$OUTPUT_DIR"
