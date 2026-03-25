#!/bin/bash --login
#SBATCH -N1 -n1
#SBATCH --cpus-per-task=10
#SBATCH --time=02:00:00
#SBATCH --job-name=aggregate-runs
#SBATCH --output=logs/aggregate_%j.log
#SBATCH --mail-user=heinrich@vsp.tu-berlin.de
#SBATCH --mail-type=BEGIN,END,FAIL

set -euo pipefail

conda activate router

cd /home/bemheinr/scratch/rust-pt-routing/parallel-qsim-berlin/src/main/python/scripts

python3 aggregate_runs.py --skip-existing --threads 10 ../../../../output/v6.4/10pct/
