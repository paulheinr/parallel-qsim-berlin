#!/bin/bash
# Partitions the Berlin networks locally, once for every number of parts in [FROM, TO].
#
# Usage: scripts/partition-networks.sh [METHOD] [PCTS] [FROM] [TO]
#   scripts/partition-networks.sh                  # metis, "1 3 10", 1..192
#   scripts/partition-networks.sh metis "1" 1 4
#
# METHOD is a file in input/partitioning/ (without .yml) and becomes part of the file name:
#   $OUT_DIR/berlin-v7.1-<pct>pct.network.<METHOD>.<NNN>.xml.zst
# Existing files are skipped, so an interrupted run can simply be restarted.
#
# Environment:
#   SCENARIO_DIR  MATSim scenario with calibrated-<pct>pct/output/ (default: public-svn next to ~/git)
#   OUT_DIR       output directory (default: shared-svn/projects/rust-qsim/berlin-v7.1/network next to ~/git)

set -euo pipefail

METHOD=${1:-metis}
PCTS=${2:-"1 3 10"}
FROM=${3:-1}
TO=${4:-192}

REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
VERSION=v7.1
SCENARIO_DIR=${SCENARIO_DIR:-"$REPO/../../public-svn/matsim/scenarios/countries/de/berlin/berlin-$VERSION"}
OUT_DIR=${OUT_DIR:-"$REPO/../../shared-svn/projects/rust-qsim/berlin-$VERSION/network"}
METHOD_FILE="$REPO/input/partitioning/$METHOD.yml"

if [[ ! -f $METHOD_FILE ]]; then
    echo "Method file $METHOD_FILE does not exist." >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
OUT_DIR=$(cd -- "$OUT_DIR" && pwd)

cargo build --release --manifest-path "$REPO/src/main/rust/Cargo.toml" --bin partition_networks

for pct in $PCTS; do
    "$REPO/src/main/rust/target/release/partition_networks" \
        --network "$SCENARIO_DIR/calibrated-${pct}pct/output/berlin-$VERSION-${pct}pct.output_network.xml.gz" \
        --method "$METHOD_FILE" \
        --output-dir "$OUT_DIR" \
        --prefix "berlin-$VERSION.network" \
        --from "$FROM" --to "$TO" \
        --skip-existing
done

echo
echo "Done. Networks are in $OUT_DIR"
