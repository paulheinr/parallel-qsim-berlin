#!/usr/bin/env bash
# Builds the bundle of the raptor benchmark (step B6 of the design doc on exogenous pt delays,
# docs/exogenous-pt-delays.md): everything run.sh needs, so that the benchmark runs locally or on Lise
# without Maven, matsim-libs or a build of this repository there. Run from the repository root:
#
#   scripts/raptor-benchmark/bundle.sh <bundle dir>
#
# The bundle contains:
#   matsim-base.jar, matsim-branch.jar  the matsim module at BASE_REV and BRANCH_REV, built from git archive
#   classes.jar, test-classes.jar       this repository (RaptorBenchmark and TimetableUpdateBenchmark are test classes)
#   lib/NNNN-<name>.jar                 the other jars of the test classpath, numbered in Maven's order
#   bundle.txt                          the commits and the checksums of the matsim jars
#   run.sh, slurm.sh                    copies of the scripts next to this one
#
# Environment, with defaults:
#   MATSIM_LIBS=../matsim-libs   checkout of matsim-libs; only read with git archive, its working tree is not touched
#   BASE_REV=bd2ff64ce56         base of ph/raptor-timetable; its matsim module is identical to the release 2027.0-2026w45
#   BRANCH_REV=ee6bd3c66a0       head of ph/raptor-timetable (B4)
# The matsim jars are built once and kept in output/benchmark/raptor/jars/.

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <bundle dir>" >&2
  exit 1
fi
BUNDLE=$1
MATSIM_LIBS=${MATSIM_LIBS:-../matsim-libs}
BASE_REV=${BASE_REV:-bd2ff64ce56}
BRANCH_REV=${BRANCH_REV:-ee6bd3c66a0}
JARS=output/benchmark/raptor/jars

if [ -e "$BUNDLE" ]; then
  echo "$BUNDLE exists already." >&2
  exit 1
fi
mkdir -p "$JARS" "$BUNDLE/lib"

# Builds the matsim module of commit $1 from git archive, without tests, into $JARS/matsim-$1.jar.
build_matsim() {
  local rev=$1
  local jar=$JARS/matsim-$rev.jar
  if [ -f "$jar" ]; then
    return
  fi
  local src
  src=$(mktemp -d)
  echo "Building matsim at $rev in $src"
  git -C "$MATSIM_LIBS" archive "$rev" pom.xml matsim | tar -x -C "$src"
  mvn -q -B -f "$src/matsim/pom.xml" package -Dmaven.test.skip=true -Dsource.skip=true
  cp "$(find "$src/matsim/target" -maxdepth 1 -name 'matsim-*.jar' ! -name '*-tests.jar' ! -name '*-sources.jar')" "$jar"
  rm -rf "$src"
}

build_matsim "$BASE_REV"
build_matsim "$BRANCH_REV"
cp "$JARS/matsim-$BASE_REV.jar" "$BUNDLE/matsim-base.jar"
cp "$JARS/matsim-$BRANCH_REV.jar" "$BUNDLE/matsim-branch.jar"

echo "Compiling parallel-qsim-berlin and collecting its classpath"
CLASSPATH_FILE=$(mktemp)
./mvnw -q -B test-compile dependency:build-classpath -Dmdep.includeScope=test -Dmdep.outputFile="$CLASSPATH_FILE"
# the matsim jar of the build, replaced by matsim-base.jar or matsim-branch.jar in run.sh
SNAPSHOT_JAR=$(tr ':' '\n' < "$CLASSPATH_FILE" | grep '/org/matsim/matsim/[^/]*/matsim-[^/]*\.jar$' | grep -v -- '-tests\.jar$' || true)
if [ -z "$SNAPSHOT_JAR" ] || [ "$(echo "$SNAPSHOT_JAR" | wc -l)" -ne 1 ]; then
  echo "Expected exactly one matsim jar in the classpath, found: $SNAPSHOT_JAR" >&2
  exit 1
fi
i=0
# the file has no final newline, so without the echo read would miss the last jar
while read -r jar; do
  if [ -z "$jar" ] || [ "$jar" = "$SNAPSHOT_JAR" ]; then
    continue
  fi
  i=$((i + 1))
  cp "$jar" "$BUNDLE/lib/$(printf '%04d' "$i")-$(basename "$jar")"
done < <(tr ':' '\n' < "$CLASSPATH_FILE"; echo)
EXPECTED=$(($(tr ':' '\n' < "$CLASSPATH_FILE" | grep -c .) - 1))
rm "$CLASSPATH_FILE"
if [ "$i" -ne "$EXPECTED" ]; then
  echo "Copied $i jars, but the classpath has $EXPECTED besides matsim." >&2
  exit 1
fi
jar cf "$BUNDLE/classes.jar" -C target/classes .
jar cf "$BUNDLE/test-classes.jar" -C target/test-classes .
cp scripts/raptor-benchmark/run.sh scripts/raptor-benchmark/slurm.sh "$BUNDLE/"

{
  echo "bundle built: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "build jdk: $(java -version 2>&1 | head -1)"
  echo "parallel-qsim-berlin: $(git rev-parse --short HEAD)$(git diff --quiet HEAD || echo ' (with local changes)')"
  echo "base: $BASE_REV, sha256 $(shasum -a 256 "$BUNDLE/matsim-base.jar" | cut -d' ' -f1)"
  echo "branch: $BRANCH_REV, sha256 $(shasum -a 256 "$BUNDLE/matsim-branch.jar" | cut -d' ' -f1)"
  echo "lib: $i jars"
} > "$BUNDLE/bundle.txt"
cat "$BUNDLE/bundle.txt"
echo "Bundle in $BUNDLE ($(du -sh "$BUNDLE" | cut -f1))"
