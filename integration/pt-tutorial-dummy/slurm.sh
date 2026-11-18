#!/bin/bash --login
# pt-tutorial-dummy on Slurm (Lise), the counterpart of process-compose.yml: hetjob with the router as component 0 and
# the simulation as component 1. Submit from the repository root:
#
#   ROUTER_JAR=... SIM_BIN=... COMPARE_BIN=... sbatch integration/pt-tutorial-dummy/slurm.sh
#
# The simulation retries connecting until the router is ready and stops it at its end. The job ends with the exit
# code of compare_events. If a step fails, the job ends and Slurm stops the other one.

#SBATCH --job-name=integration-pt-tutorial-dummy
#SBATCH --time=00:10:00
#SBATCH --output=slurm-integration-pt-tutorial-dummy-%j.log
#SBATCH --partition=cpu-genoa:test
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH hetjob
#SBATCH --partition=cpu-genoa:test
#SBATCH --nodes=1
#SBATCH --ntasks=1

set -euo pipefail

SCENARIO=integration/pt-tutorial-dummy
OUTPUT=output/$SCENARIO
ROUTER_NODE=$(scontrol show hostnames "$SLURM_JOB_NODELIST_HET_GROUP_0" | head -n 1)

srun --het-group=0 java -Dmatsim.preferLocalDtds=true -jar "$ROUTER_JAR" \
    --config "$SCENARIO/input/router-config.xml" --threads 1 --port 50051 --output "$OUTPUT/router" &
ROUTER_PID=$!

srun --het-group=1 "$SIM_BIN" --config "$SCENARIO/input/sim-config.yml" \
    --router-ip "http://$ROUTER_NODE.ib.hlrn.de:50051"
wait "$ROUTER_PID"
