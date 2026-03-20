#!/bin/bash --login
#SBATCH -N1 -n1
#SBATCH --partition=cpu-genoa
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
#SBATCH --job-name=data-preprocessing
#SBATCH --output=logs/data_preprocessing_%j.log
#SBATCH --mail-user=heinrich@vsp.tu-berlin.de
#SBATCH --mail-type=BEGIN,END,FAIL

set -euo pipefail

conda activate router

CMD="python3 -u /home/bemheinr/scratch/rust-pt-routing/parallel-qsim-berlin/src/main/python/preprocessing.py --root /home/bemheinr/scratch/rust-pt-routing/parallel-qsim-berlin/output/v6.4 --instrument False"

echo "command = $CMD"

eval $CMD
