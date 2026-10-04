#!/bin/bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
mkdir -p output/logs

for pct in 1 10; do
    case "$pct" in
        1) WALL_TIME=00:10:00 ;;
        10) WALL_TIME=00:30:00 ;;
    esac

    for threads in 1 2 4 8 16 32 64 128 192; do
        sbatch --time="$WALL_TIME" \
            scripts/run-berlin-iterations-v7.sh "$threads" "$pct"
    done
done
