#!/bin/bash
# Issue #97 -- Linux validation of the port, on cpu64.
#
# Both trees are real clones checked out from the remote: the base at the PR's merge
# base and the candidate at the PR branch itself, so nothing in the trust chain depends
# on a patch file that is not in the repository. A copied build tree would cache an
# absolute source path and rebuild the original sources, so the two builds are separate
# and out of tree.
set -u
ROOT=${ROOT:-/home/ubuntu/mc-issue97-port}
MAIN=${MAIN:?set MAIN to the base commit}
BRANCH=${BRANCH:-fix/issue-97-recenter-port}
REPO=${REPO:-https://github.com/KingAlejandro/MotionCorr-standalone.git}
CPUS=${CPUS:-40-55}        # node 1, away from the long-running ctffind jobs
MEMNODE=${MEMNODE:-1}
JOBS=${JOBS:-16}
export PATH=/home/ubuntu/.mc-venv/bin:$PATH   # cmake/ctest live only here on cpu64
PY=/home/ubuntu/.mc-venv/bin/python
CMAKE=/home/ubuntu/.mc-venv/bin/cmake

mkdir -p "$ROOT"; exec >>"$ROOT/run.log" 2>&1
echo "############ START $(date -Is) ############"
exec 9>/tmp/motioncorr-issue96-cpu-validation.lock
echo "[lock] waiting"; T0=$(date +%s)
flock -w 10800 9 || { echo "STATUS=LOCK_TIMEOUT"; exit 90; }
echo "[lock] acquired after $(( $(date +%s) - T0 ))s at $(date -Is)"
PIN=(taskset -c "$CPUS" numactl --membind="$MEMNODE")
run() { echo; echo "\$ $*"; "$@"; echo "exit=$?"; }

echo "===== PROVENANCE ====="
run hostname; run uname -r
lscpu | grep -E "^Model name|^CPU\(s\)|^Thread|^NUMA node[01] CPU"
"${PIN[@]}" bash -c 'grep -E "Cpus_allowed_list|Mems_allowed_list" /proc/self/status'
echo "--- load at start ---"; cat /proc/loadavg
echo "--- other users of cores 32-63 ---"
ps -eo pid,user,pcpu,psr,etimes,comm --sort=-pcpu | awk 'NR==1 || ($4>=32 && $4<=63 && $3>1.0)'
run "$CMAKE" --version; run "$PY" --version; run gcc --version

echo; echo "===== SOURCE (two independent clones, checked out from the remote) ====="
for name in base fixed; do
    d=$ROOT/src-$name; rm -rf "$d"; git clone -q "$REPO" "$d"
done
git -C "$ROOT/src-base"  checkout -q --force --detach "$MAIN"
git -C "$ROOT/src-fixed" checkout -q --force --detach "origin/$BRANCH"
for name in base fixed; do
    d=$ROOT/src-$name
    echo "[$name] HEAD=$(git -C "$d" rev-parse HEAD)  tree=$(git -C "$d" rev-parse 'HEAD^{tree}')  dirty=$(git -C "$d" status --porcelain | wc -l)"
done
echo "--- every file that differs between the two trees ---"
run git -C "$ROOT/src-fixed" diff --stat "$MAIN" HEAD
echo "--- production delta, whole of src/ ---"
run diff -r "$ROOT/src-base/src" "$ROOT/src-fixed/src"
echo "--- hashes of the sources and of the analysis scripts that run below ---"
sha256sum "$ROOT"/src-*/src/motioncorr_runner.cpp "$ROOT"/src-*/src/motioncorr_runner.h \
          "$ROOT"/src-fixed/tests/test_runner_contract.py \
          "$ROOT"/src-fixed/tests/test_runner_numerics.cpp \
          "$ROOT"/src-fixed/docs/issue97_cpu_evidence/port_assertion_margins.py \
          "$ROOT"/src-fixed/docs/issue97_cpu_evidence/port_option_off_control.py

echo; echo "===== BUILD (Release, -j$JOBS, pinned, out of tree) ====="
for name in base fixed; do
    s=$ROOT/src-$name; b=$ROOT/build-$name; rm -rf "$b"
    "${PIN[@]}" "$CMAKE" -S "$s" -B "$b" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
        -DPython3_EXECUTABLE="$PY" >"$ROOT/cfg-$name.log" 2>&1
    echo "[$name] configure exit=$?"
    "${PIN[@]}" "$CMAKE" --build "$b" -j"$JOBS" >"$ROOT/bld-$name.log" 2>&1
    echo "[$name] build exit=$?"
    grep -E '^CMAKE_BUILD_TYPE|^CMAKE_HOME_DIRECTORY' "$b/CMakeCache.txt" | sed 's/^/  /'
    echo "  sha256 binary: $(sha256sum "$b/motioncorr")"
done

echo; echo "===== COLLECTION GATE ====="
echo "--- candidate validator on the candidate build: must PASS ---"
run "${PIN[@]}" "$PY" "$ROOT/src-fixed/tools/validate_test_collection.py" --test-dir "$ROOT/build-fixed"
echo "--- the same validator on the BASE build: must FAIL ---"
run "${PIN[@]}" "$PY" "$ROOT/src-fixed/tools/validate_test_collection.py" --test-dir "$ROOT/build-base"

echo; echo "===== FULL CTEST ====="
for name in fixed base; do
    "${PIN[@]}" ctest --test-dir "$ROOT/build-$name" -j4 --output-on-failure >"$ROOT/ctest-$name.log" 2>&1
    echo "[$name] ctest exit=$?"; tail -4 "$ROOT/ctest-$name.log"
done
echo "--- the two new cases must not exist on base ---"
run "${PIN[@]}" ctest --test-dir "$ROOT/build-base" -R RunnerInterpolate -N

echo; echo "===== NEW CASE: positive and negative control ====="
echo "--- candidate binary: must pass ---"
run "${PIN[@]}" "$PY" "$ROOT/src-fixed/tests/test_runner_contract.py" \
    --binary "$ROOT/build-fixed/motioncorr" --case interpolate_shifts
echo "--- BASE binary, same test: must fail, proving the call site is covered ---"
run "${PIN[@]}" "$PY" "$ROOT/src-fixed/tests/test_runner_contract.py" \
    --binary "$ROOT/build-base/motioncorr" --case interpolate_shifts
echo "--- unit regression ---"
run "${PIN[@]}" "$ROOT/build-fixed/runner_numerics" interpolate_recenter

echo; echo "===== PER-ASSERTION OUTCOME AND MARGINS ====="
run "${PIN[@]}" "$PY" "$ROOT/src-fixed/docs/issue97_cpu_evidence/port_assertion_margins.py" \
    "$ROOT/build-base/motioncorr" "$ROOT/build-fixed/motioncorr" \
    "$ROOT/src-fixed/test-data/fixtures" "$ROOT/src-fixed/tests"

echo; echo "===== DEFAULT-OFF EXACTNESS CONTROL ====="
run "${PIN[@]}" "$PY" "$ROOT/src-fixed/docs/issue97_cpu_evidence/port_option_off_control.py" \
    "$ROOT/build-base/motioncorr" "$ROOT/build-fixed/motioncorr" \
    "$ROOT/src-fixed/test-data/fixtures"

echo; echo "--- load at end ---"; cat /proc/loadavg
echo "STATUS=DONE"
echo "############ END $(date -Is) ############"
