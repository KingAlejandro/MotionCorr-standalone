#!/usr/bin/env bash
# CPU validation of the #53 static-worker port on the Linux validation host.
#
# Runs on cpu64 under flock /tmp/motioncorr-issue96-cpu-validation.lock, confined
# to cores 32-63 (NUMA node 1), build -j 16, per the #66/#96 resource rules.
#
# Layers, in order, each fail-closed:
#   1. provenance and AppleDouble assertion on the staged tree
#   2. Release build; abort on a nonzero build rc rather than testing a stale artifact
#   3. tests/test_multi_gpu_scheduling.py against the real built binary
#   4. docs/multi_gpu/negative_controls.py mutation controls
#   5. tools/validate_test_collection.py fail-closed collection check
#   6. full ctest
#   7. end-to-end: serial vs 3-way sharded over the real binary, merge, exact compare
#
# Usage: cpu64_port_validation.sh <root>   (root holds src/ and is writable scratch)
#
# `src` must be a GIT-BACKED working tree, not a `git archive` extract:
# CiFailClosedControls control 6 verifies the canonical fixture manifest through
# `--repo <src> --ref HEAD`, and an extract with no .git takes the source-archive
# fallback path and fails on a different message. Control 2 shells out to `cmake`
# by name, so the venv must be on PATH for the whole script, not just the steps
# that call cmake directly. Both are properties of the harness; getting either
# wrong produces a failure that looks like a source defect.
set -euo pipefail
set -x

ROOT="${1:?usage: cpu64_port_validation.sh <root>}"
SRC="$ROOT/src"
BUILD="$ROOT/build"
VENV="$HOME/.mc-venv"
PY="$VENV/bin/python3"
CMAKE="$VENV/bin/cmake"
CTEST="$VENV/bin/ctest"
MASK="32-63"
export PATH="$VENV/bin:$PATH"

echo "=== PROVENANCE ==="
cat "$ROOT/src_head.txt"
applefile_count=$(find "$SRC" -name '._*' | wc -l)
echo "applefile_count=$applefile_count"
[ "$applefile_count" -eq 0 ]
git -C "$SRC" rev-parse HEAD
git -C "$SRC" status --porcelain
[ -z "$(git -C "$SRC" status --porcelain)" ]

echo "=== HOST / TOPOLOGY / LOAD AT START ==="
date -Is; hostname; grep Cpus_allowed_list /proc/self/status; cat /proc/loadavg
echo '--- concurrent MotionCorr work (recorded, not altered) ---'
pgrep -alf motioncorr | grep -v pgrep | grep -v "$ROOT" | head -5 || true
echo '--- ctffind (untouched) ---'
pgrep -c ctffind || true

echo "=== BUILD (Release, CUDA=OFF, -j16 on $MASK) ==="
rm -rf "$BUILD"
taskset -c "$MASK" "$CMAKE" -S "$SRC" -B "$BUILD" \
    -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON \
    -DPython3_EXECUTABLE="$PY"
set +e
taskset -c "$MASK" "$CMAKE" --build "$BUILD" -j 16
BUILD_RC=$?
set -e
echo "BUILD_RC=$BUILD_RC"
[ "$BUILD_RC" -eq 0 ]
sha256sum "$BUILD/motioncorr"
grep -m1 '^CMAKE_BUILD_TYPE' "$BUILD/CMakeCache.txt"
grep -m1 CXX_FLAGS "$BUILD/CMakeFiles/motioncorr_core.dir/flags.make"
g++ --version | head -1
"$CMAKE" --version | head -1
"$PY" --version
"$PY" -c 'import numpy; print("numpy", numpy.__version__)'

echo "=== SCHEDULING SUITE (real binary) ==="
set +e
taskset -c "$MASK" "$PY" "$SRC/tests/test_multi_gpu_scheduling.py" --binary "$BUILD/motioncorr"
SCHED_RC=$?
set -e
echo "SCHED_RC=$SCHED_RC"

echo "=== NEGATIVE CONTROLS ==="
set +e
taskset -c "$MASK" "$PY" "$SRC/docs/multi_gpu/negative_controls.py" \
    --json-out "$ROOT/negative_controls.json"
NEGCTL_RC=$?
set -e
echo "NEGCTL_RC=$NEGCTL_RC"

echo "=== TEST COLLECTION (fail-closed) ==="
set +e
PATH="$VENV/bin:$PATH" taskset -c "$MASK" "$PY" "$SRC/tools/validate_test_collection.py" \
    --test-dir "$BUILD" --dump-json "$ROOT/test_collection.json"
COLLECT_RC=$?
set -e
echo "COLLECT_RC=$COLLECT_RC"

echo "=== FULL CTEST ==="
set +e
cd "$BUILD" && taskset -c "$MASK" "$CTEST" --output-on-failure -j 4
CTEST_RC=$?
set -e
echo "CTEST_RC=$CTEST_RC"

echo "=== END-TO-END: serial vs 3-way sharded, real binary ==="
set +e
taskset -c "$MASK" "$PY" "$SRC/docs/multi_gpu/port_validation/e2e_cpu_arm.py" \
    --binary "$BUILD/motioncorr" --src "$SRC" --work "$ROOT/e2e" \
    --json-out "$ROOT/e2e_summary.json"
E2E_RC=$?
set -e
echo "E2E_RC=$E2E_RC"

echo "=== LOAD AT END ==="
date -Is; cat /proc/loadavg
echo "SUMMARY BUILD_RC=$BUILD_RC SCHED_RC=$SCHED_RC NEGCTL_RC=$NEGCTL_RC COLLECT_RC=$COLLECT_RC CTEST_RC=$CTEST_RC E2E_RC=$E2E_RC"
