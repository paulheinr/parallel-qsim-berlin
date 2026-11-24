#!/usr/bin/env bash
# Runs the raptor benchmark (step B6 of the design doc on exogenous pt delays) from a bundle of bundle.sh, locally or in
# the job of slurm.sh. Run from the root of a checkout of this repository, which provides
# integration/berlin/router-config.xml; its relative paths, and those in RaptorBenchmark, lead to public-svn:
#
#   <bundle>/run.sh <bundle> <output dir> [options of RaptorBenchmark, e.g. --sample 200 --warmup 1 --rounds 2]
#
# Variants (label/variant, see RaptorVariants): base/schedule (matsim before the change), branch/schedule,
# branch/option and branch/versioned. Each fork runs every variant in its own JVM, in a rotating order, so that the
# order does not favour a variant. Only the matsim jar differs between base and branch. Afterwards
# TimetableUpdateBenchmark runs once with the branch.
#
# Environment, with defaults:
#   FORKS=5                     runs per variant
#   VARIANTS="base/schedule branch/schedule branch/option branch/versioned"
#                               the variants of each fork, label/variant separated by spaces
#   JAVA=java
#   JAVA_OPTS="-Xms8g -Xmx8g"
#   JFR=0                       1 records a profile of each run with JFR (profile-<label>-<variant>-<fork>.jfr, a method
#                               sample every ms, with DebugNonSafepoints); its times then include the overhead of JFR
#   UPDATES=1                   0 skips TimetableUpdateBenchmark
#
# Output: log-*.txt per run and machine.txt, the other files see RaptorBenchmark and TimetableUpdateBenchmark. With the
# defaults (2000 trips, 3 + 10 rounds, 5 forks) it takes about 45 min on a Mac M4 Max and 50 min on a Genoa node of
# Lise. Summary, in src/main/python:
#
#   uv run --group analysis python scripts/raptor_benchmark.py <output dir>

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <bundle> <output dir> [options of RaptorBenchmark]" >&2
  exit 1
fi
BUNDLE=$(cd "$1" && pwd)
OUT=$2
shift 2

FORKS=${FORKS:-5}
VARIANTS=${VARIANTS:-"base/schedule branch/schedule branch/option branch/versioned"}
JAVA=${JAVA:-java}
JAVA_OPTS=${JAVA_OPTS:-"-Xms8g -Xmx8g"}
JFR=${JFR:-0}
UPDATES=${UPDATES:-1}

if [ -e "$OUT/rounds.csv" ]; then
  echo "$OUT already has results, choose another output directory." >&2
  exit 1
fi
mkdir -p "$OUT"

LIB=$(ls "$BUNDLE"/lib/*.jar | paste -s -d : -)
# The classpath with matsim-$1.jar.
classpath() {
  echo "$BUNDLE/test-classes.jar:$BUNDLE/classes.jar:$BUNDLE/matsim-$1.jar:$LIB"
}

{
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host: $(hostname)${SLURM_JOB_ID:+, job $SLURM_JOB_ID}"
  echo "machine: $(sysctl -n machdep.cpu.brand_string 2>/dev/null || grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | sed 's/^ //' || echo unknown)"
  echo "java: $("$JAVA" -version 2>&1 | head -1)"
  echo "java options: $JAVA_OPTS"
  echo "forks: $FORKS"
  echo "variants: $VARIANTS"
  echo "jfr: $JFR"
  echo "options: $*"
  cat "$BUNDLE/bundle.txt"
} > "$OUT/machine.txt"
cat "$OUT/machine.txt"

read -r -a RUNS <<< "$VARIANTS"
for run in "${RUNS[@]}"; do
  if [[ ! $run =~ ^(base/schedule|branch/(schedule|option|versioned))$ ]]; then
    echo "Unknown variant $run in VARIANTS=$VARIANTS" >&2
    exit 1
  fi
done
for ((fork = 1; fork <= FORKS; fork++)); do
  for ((i = 0; i < ${#RUNS[@]}; i++)); do
    run=${RUNS[$(((i + fork - 1) % ${#RUNS[@]}))]}
    label=${run%%/*}
    variant=${run#*/}
    echo "$(date +%H:%M:%S) fork $fork: $label/$variant"
    profile=()
    if [ "$JFR" = 1 ]; then
      # without DebugNonSafepoints, JFR attributes the samples in small inlined methods (such as the lookups of the
      # timetable) to the method they are inlined into
      profile=(-XX:+UnlockDiagnosticVMOptions -XX:+DebugNonSafepoints
        "-XX:StartFlightRecording:filename=$OUT/profile-$label-$variant-$fork.jfr,settings=profile,method-profiling=max")
    fi
    # shellcheck disable=SC2086
    "$JAVA" $JAVA_OPTS ${profile[@]+"${profile[@]}"} -Dmatsim.preferLocalDtds=true -cp "$(classpath "$label")" org.matsim.routing.RaptorBenchmark \
      --label "$label" --variant "$variant" --fork "$fork" --output "$OUT" "$@" > "$OUT/log-$label-$variant-$fork.txt" 2>&1
  done
done

if [ "$UPDATES" = 1 ]; then
  echo "$(date +%H:%M:%S) TimetableUpdateBenchmark"
  # shellcheck disable=SC2086
  "$JAVA" $JAVA_OPTS -Dmatsim.preferLocalDtds=true -cp "$(classpath branch)" org.matsim.routing.TimetableUpdateBenchmark \
    --output "$OUT" > "$OUT/log-updates.txt" 2>&1
fi
echo "$(date +%H:%M:%S) done: $OUT"
