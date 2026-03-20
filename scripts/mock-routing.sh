#!/bin/bash --login
#SBATCH -N2 -n2
#SBATCH --partition=cpu-genoa
#SBATCH --cpus-per-task=192
#SBATCH --time=01:00:00
#SBATCH --job-name=mock-routing
#SBATCH --output=logs/mock-routing_%j.log
#SBATCH --mail-user=heinrich@vsp.tu-berlin.de
#SBATCH --mail-type=BEGIN,END,FAIL

set -euo pipefail

# ----------------------------------------------------------------------
# 1) Argument parsing: key=value --> environment variables
#    Allows: sbatch run.sh THREADS=192 ...
# ----------------------------------------------------------------------
for ARGUMENT in "$@"; do
   KEY=$(echo "$ARGUMENT" | cut -f1 -d=)
   KEY_LENGTH=${#KEY}
   VALUE="${ARGUMENT:$KEY_LENGTH+1}"

   export "$KEY"="$VALUE"
   echo "Start script with argument: $KEY=$VALUE"
done

# ----------------------------------------------------------------------
# 2) Defaults for all configuration parameters
# ----------------------------------------------------------------------
THREADS=${THREADS:-192} # Java router threads
NUMA=${NUMA:-""}

echo "Effective configuration:"
echo "  THREADS = $THREADS"
echo "  NUMA = $NUMA"

# ----------------------------------------------------------------------
# 3) Node assignment (simulation client vs routing server)
# ----------------------------------------------------------------------
nodes=($(scontrol show hostnames "$SLURM_NODELIST"))
server_node="${nodes[0]}"
client_node="${nodes[1]}"
server_host_ib="${server_node}.ib.hlrn.de"

echo "Current hostname: $(hostname)"
echo "Server node: $server_node"
echo "Client node: $client_node"
echo "Server IB hostname: $server_host_ib"

# ----------------------------------------------------------------------
# 4) Logging setup
# ----------------------------------------------------------------------
LOG_DIR="$PWD/logs"
mkdir -p "$LOG_DIR"
JOB_SUFFIX=${SLURM_JOB_ID:-$(date +%s)}

CONFIG_TAG="mock_routing${THREADS}"
echo "Log configuration tag: $CONFIG_TAG"

# ----------------------------------------------------------------------
# 5) Environment setup (Conda etc.)
# ----------------------------------------------------------------------
which conda
conda --version

conda activate routing

# Disable colored output for cleaner logs
export NO_COLOR=1

# ----------------------------------------------------------------------
# 7) Start the client (Rust simulation)
# ----------------------------------------------------------------------

(
  cd parallel-qsim-berlin
  srun -N1 -n1 -w "$client_node" \
    --output="$LOG_DIR/${CONFIG_TAG}_${JOB_SUFFIX}_client.log" \
    java -Xmx500G -XX:+UseG1GC -cp parallel-qsim-berlin-1.0-*.jar org.matsim.analysis.MockRoutingClient --ip "$server_host_ib" --port "50051" --requestsFile "berlin_v6.4_10pct_requests.pb"
) &

# Short delay to ensure the client is up before the router starts
sleep 2

# ----------------------------------------------------------------------
# 8) Start the server (Java gRPC router)
# ----------------------------------------------------------------------
(
  cd parallel-qsim-berlin
  srun -N1 -n1 -w "$server_node" \
    --output="$LOG_DIR/${CONFIG_TAG}_${JOB_SUFFIX}_server.log" \
    make router \
      THREADS="$THREADS" \
      MEMORY=500G \
      PCT=10 \
      RUN_ID="$CONFIG_TAG" \
      JVM_ARGS_EXTRA="$NUMA"
) &

# ----------------------------------------------------------------------
# 9) Wait for both processes to complete
# ----------------------------------------------------------------------
wait

echo "Run completed for configuration: $CONFIG_TAG"
