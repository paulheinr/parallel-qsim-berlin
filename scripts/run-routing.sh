#!/bin/bash --login
#SBATCH --partition=cpu-genoa
#SBATCH --cpus-per-task=192
#SBATCH --time=01:00:00
#SBATCH --job-name=rust-qsim-routing
#SBATCH --output=logs/rust-qsim-routing_%j.log
#SBATCH --mail-user=heinrich@vsp.tu-berlin.de
#SBATCH --mail-type=BEGIN,END,FAIL

set -euo pipefail

# ----------------------------------------------------------------------
# 1) Argument parsing: key=value --> environment variables
#    Allows: sbatch run.sh SIM_CPUS=64 HORIZON=600 WORKER_THREADS=4 ROUTER_THREADS=192 ...
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
SIM_CPUS=${SIM_CPUS:-192}             # passed to Rust as N
HORIZON=${HORIZON:-600}               # selects the population file
WORKER_THREADS=${WORKER_THREADS:-4}   # async worker threads in Rust
ROUTER_THREADS=${ROUTER_THREADS:-192} # Java router threads
PCT=${PCT:-1}

# Calculate threads per routing node (each node can handle up to 24 threads)
THREADS_PER_NODE=24
NUM_ROUTING_NODES=$(( (ROUTER_THREADS + THREADS_PER_NODE - 1) / THREADS_PER_NODE ))
THREADS_PER_SERVER=$(( (ROUTER_THREADS + NUM_ROUTING_NODES - 1) / NUM_ROUTING_NODES ))

echo "Effective configuration:"
echo "  SIM_CPUS           = $SIM_CPUS"
echo "  HORIZON            = $HORIZON"
echo "  WORKER_THREADS     = $WORKER_THREADS"
echo "  ROUTER_THREADS     = $ROUTER_THREADS"
echo "  PCT                = $PCT"
echo "  NUM_ROUTING_NODES  = $NUM_ROUTING_NODES"
echo "  THREADS_PER_SERVER = $THREADS_PER_SERVER"

# Internal names expected by the Makefiles
N="$SIM_CPUS"

# ----------------------------------------------------------------------
# 3) Node assignment (simulation client vs routing servers)
#    Node 0 = client, Nodes 1..N = routing servers
# ----------------------------------------------------------------------
nodes=($(scontrol show hostnames "$SLURM_NODELIST"))
client_node="${nodes[0]}"

# Build arrays for server nodes and URLs
server_nodes=()
server_urls=""
for (( i=1; i<=NUM_ROUTING_NODES; i++ )); do
    server_node="${nodes[$i]}"
    server_nodes+=("$server_node")
    server_host_ib="${server_node}.ib.hlrn.de"
    if [[ -n "$server_urls" ]]; then
        server_urls+=" "
    fi
    server_urls+="http://${server_host_ib}:50051"
done

echo "Current hostname: $(hostname)"
echo "Client node: $client_node"
echo "Server nodes: ${server_nodes[*]}"
echo "Server URLs: $server_urls"

# ----------------------------------------------------------------------
# 4) Logging setup
# ----------------------------------------------------------------------
LOG_DIR="$PWD/logs"
mkdir -p "$LOG_DIR"
JOB_SUFFIX=${SLURM_JOB_ID:-$(date +%s)}

CONFIG_TAG="sim${SIM_CPUS}_hor${HORIZON}_w${WORKER_THREADS}_r${ROUTER_THREADS}_${PCT}pct"
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
# 6) Assemble ARGS for the Rust client
# ----------------------------------------------------------------------

# Example population file path with horizon encoded

ARGS=""
ARGS+=" --set computational_setup.adapter_worker_threads=${WORKER_THREADS}"
ARGS+=" --set output.output_dir=/home/bemheinr/scratch/rust-pt-routing/parallel-qsim-berlin/output/v6.4/${CONFIG_TAG}"

# Optional: allow additional arguments from the outside
if [[ -n "${EXTRA_ARGS:-}" ]]; then
  ARGS+=" ${EXTRA_ARGS}"
fi

echo "Final ARGS for Rust client: $ARGS"

# ----------------------------------------------------------------------
# 7) Start the client (Rust simulation)
# ----------------------------------------------------------------------

(
  cd .. # move to parent folder
  srun -N1 -n1 -w "$client_node" \
    --output="$LOG_DIR/${CONFIG_TAG}_${JOB_SUFFIX}_client.log" \
    make run-routing \
      N="$N" \
      RUST_BASE=/home/bemheinr/scratch/rust-pt-routing/parallel-qsim-berlin/src/main/rust \
      SHARED_SVN_BASE=/home/bemheinr/scratch/rust-pt-routing/shared-svn \
      MODE=bin \
      PCT="$PCT"\
      HORIZON="$HORIZON" \
      URL="$server_urls" \
      RUN_ID="${CONFIG_TAG}_sim" \
      ARGS="$ARGS"
) &

# Short delay to ensure the client is up before the routers start
sleep 2

# ----------------------------------------------------------------------
# 8) Start the routing servers (Java gRPC routers)
# ----------------------------------------------------------------------
for (( i=0; i<NUM_ROUTING_NODES; i++ )); do
    server_node="${server_nodes[$i]}"
    (
      cd .. # move to parent folder
      srun -N1 -n1 -w "$server_node" \
        --output="$LOG_DIR/${CONFIG_TAG}_${JOB_SUFFIX}_server_${i}.log" \
        make router \
          SHARED_SVN_BASE=/home/bemheinr/scratch/rust-pt-routing/shared-svn \
          THREADS="$THREADS_PER_SERVER" \
          MEMORY=500G \
          PCT="$PCT" \
          RUN_ID="${CONFIG_TAG}_server${i}"
    ) &
done

# ----------------------------------------------------------------------
# 9) Wait for both processes to complete
# ----------------------------------------------------------------------
wait

echo "Run completed for configuration: $CONFIG_TAG"