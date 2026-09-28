#!/bin/bash
# Issue #97 CPU validation on cpu64 (small-refmac-machine).
# Runs detached under the shared validation flock. Two SEPARATE source trees:
# a copied build tree caches an absolute source path and would rebuild the
# original sources, faking a green negative control.
set -u

ROOT=/home/ubuntu/mc-issue97-grok-opus
LOG=$ROOT/run.log
CPUS=40-55          # 16 cores, all on NUMA node1 (32-63); avoids ctffind on 32 and 58
MEMNODE=1
JOBS=16
REPO=https://github.com/KingAlejandro/MotionCorr-standalone.git
BASE_SHA=4c952b3f54479653512c4d208e09c9a8c02f3726
FIXED_SHA=85dd1f9
CMAKE=/home/ubuntu/.mc-venv/bin/cmake
CTEST=/home/ubuntu/.mc-venv/bin/ctest
MOVIE=/home/ubuntu/mc-issue60/work/tutorial/Movies/20170629_00026_frameImage.tiff
GAIN=/home/ubuntu/mc-issue60/work/tutorial/Movies/gain.mrc

mkdir -p "$ROOT"
exec >>"$LOG" 2>&1
echo "############ START $(date -Is) ############"

# ---- serialize under the shared validation lock -------------------------
exec 9>/tmp/motioncorr-issue96-cpu-validation.lock
echo "[lock] waiting for /tmp/motioncorr-issue96-cpu-validation.lock ..."
LOCK_T0=$(date +%s)
if ! flock -w 10800 9; then
    echo "[lock] FAILED to acquire within 3h; aborting"; echo "STATUS=LOCK_TIMEOUT"; exit 90
fi
echo "[lock] acquired after $(( $(date +%s) - LOCK_T0 ))s at $(date -Is)"

run() { echo; echo "\$ $*"; "$@"; echo "exit=$?"; }
PIN=(taskset -c "$CPUS" numactl --membind="$MEMNODE")

# ---- environment / topology / NUMA provenance ---------------------------
echo "===== PROVENANCE ====="
run hostname
run uptime
run lscpu
echo; echo "--- NUMA hardware ---"; numactl --hardware
echo; echo "--- requested cpuset: $CPUS  membind: node$MEMNODE ---"
echo "--- actual inherited affinity of a pinned child ---"
"${PIN[@]}" bash -c 'grep Cpus_allowed_list /proc/self/status; grep Mems_allowed_list /proc/self/status; numactl --show'
echo; echo "--- CPU -> NODE/SOCKET/CORE map for my lane ---"
lscpu -p=CPU,NODE,SOCKET,CORE | grep -vE '^#' | awk -F, '$1>=40 && $1<=55'
echo; echo "--- interference: other users of cores 32-63 ---"
ps -eo pid,user,pcpu,psr,comm --sort=-pcpu | awk 'NR==1 || ($4>=32 && $4<=63 && $3>1.0)'
echo; echo "--- load at start ---"; cat /proc/loadavg

# ---- fetch two separate trees -------------------------------------------
echo; echo "===== SOURCE STAGING ====="
for pair in "base:$BASE_SHA" "fixed:$FIXED_SHA"; do
    name=${pair%%:*}; sha=${pair##*:}
    d=$ROOT/src-$name
    if [ ! -d "$d/.git" ]; then
        rm -rf "$d"; git clone -q "$REPO" "$d" || { echo "clone failed"; exit 91; }
    fi
    git -C "$d" fetch -q origin "$sha" 2>/dev/null || git -C "$d" fetch -q origin
    git -C "$d" checkout -q --detach "$sha" || { echo "checkout $sha failed"; exit 92; }
    echo "[$name] HEAD=$(git -C "$d" rev-parse HEAD)"
    echo "[$name] tree clean: $(git -C "$d" status --porcelain | wc -l) modified"
    echo "[$name] sha256 src/motioncorr_runner.cpp: $(sha256sum "$d/src/motioncorr_runner.cpp")"
    echo "[$name] sha256 src/motioncorr_runner.h:   $(sha256sum "$d/src/motioncorr_runner.h")"
done
echo "--- the ONLY production delta between the two trees ---"
diff -u "$ROOT/src-base/src/motioncorr_runner.cpp" "$ROOT/src-fixed/src/motioncorr_runner.cpp"
diff -u "$ROOT/src-base/src/motioncorr_runner.h"   "$ROOT/src-fixed/src/motioncorr_runner.h"

# ---- build both ----------------------------------------------------------
echo; echo "===== BUILD (Release, -j$JOBS, pinned) ====="
for name in base fixed; do
    s=$ROOT/src-$name; b=$ROOT/build-$name
    rm -rf "$b"; mkdir -p "$b"
    echo "--- configure $name ---"
    "${PIN[@]}" "$CMAKE" -S "$s" -B "$b" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
    echo "configure exit=$?"
    echo "--- build $name ---"
    /usr/bin/time -v "${PIN[@]}" "$CMAKE" --build "$b" -j "$JOBS" 2>&1 | tail -25
    echo "CMAKE_BUILD_TYPE: $(grep -E '^CMAKE_BUILD_TYPE' "$b/CMakeCache.txt")"
    echo "CMAKE_HOME_DIRECTORY: $(grep -E '^CMAKE_HOME_DIRECTORY' "$b/CMakeCache.txt")"
    echo "[$name] sha256 binary: $(sha256sum "$b/motioncorr" 2>/dev/null)"
    echo "[$name] binary opt level check:"; strings "$b/motioncorr" 2>/dev/null | grep -m1 -i "GCC:" || true
done

# ---- unit regression -----------------------------------------------------
echo; echo "===== UNIT REGRESSION ====="
echo "--- fixed tree: the new case must exist and pass ---"
"${PIN[@]}" "$CTEST" --test-dir "$ROOT/build-fixed" -R RunnerInterpolateRecenter --output-on-failure
echo "ctest exit=$?"
echo "--- fixed tree: direct invocation ---"
"${PIN[@]}" "$ROOT/build-fixed/runner_numerics" interpolate_recenter; echo "exit=$?"
echo "--- base tree: the case must NOT exist (proves it is new) ---"
"${PIN[@]}" "$CTEST" --test-dir "$ROOT/build-base" -R RunnerInterpolateRecenter -N 2>&1 | tail -3
echo "--- full suite, fixed tree (bounded) ---"
"${PIN[@]}" "$CTEST" --test-dir "$ROOT/build-fixed" -j4 2>&1 | tail -30
echo "full-suite ctest exit=$?"
echo "--- full suite, base tree (baseline for comparison) ---"
"${PIN[@]}" "$CTEST" --test-dir "$ROOT/build-base" -j4 2>&1 | tail -30
echo "base full-suite ctest exit=$?"

# ---- integration arms ----------------------------------------------------
echo; echo "===== INTEGRATION: option-off / option-on x base / fixed ====="
echo "input hashes:"
sha256sum "$ROOT/src-fixed/test-data/fixtures/synthetic_128x128_8frames.mrcs"
sha256sum "$MOVIE" "$GAIN"

arm () {   # arm <label> <binary> <extra-args...>
    local label=$1; shift
    local bin=$1; shift
    local out=$ROOT/out/$label
    rm -rf "$out"; mkdir -p "$out"
    echo; echo "########## ARM $label ##########"
    echo "\$ $bin $*"
    /usr/bin/time -v "${PIN[@]}" "$bin" "$@" --o "$out/" >"$out/stdout.log" 2>"$out/time.log"
    echo "exit=$?"
    tail -3 "$out/time.log" | grep -E "Maximum resident|Elapsed" || true
    grep -E "Patches:|Too few patches|Local alignments|interpolate_shifts|Iteration" "$out"/*.log 2>/dev/null | head -12
    echo "--- products ---"
    find "$out" -type f \( -name '*.mrc' -o -name '*.star' \) | sort | while read -r f; do
        echo "  $(sha256sum "$f")"
    done
}

SYN=$ROOT/src-fixed/test-data/fixtures/synthetic_128x128_8frames.mrcs
for tree in base fixed; do
    BIN=$ROOT/build-$tree/motioncorr
    arm "syn-$tree-off" "$BIN" --i "$SYN" --use_own --j $JOBS --patch_x 3 --patch_y 3 --angpix 1 --voltage 300 --dose_per_frame 1
    arm "syn-$tree-on"  "$BIN" --i "$SYN" --use_own --j $JOBS --patch_x 3 --patch_y 3 --angpix 1 --voltage 300 --dose_per_frame 1 --interpolate_shifts
done
for tree in base fixed; do
    BIN=$ROOT/build-$tree/motioncorr
    arm "mov-$tree-off" "$BIN" --i "$MOVIE" --use_own --j $JOBS --patch_x 5 --patch_y 5 --angpix 0.885 --voltage 200 --dose_per_frame 1.277 --gainref "$GAIN"
    arm "mov-$tree-on"  "$BIN" --i "$MOVIE" --use_own --j $JOBS --patch_x 5 --patch_y 5 --angpix 0.885 --voltage 200 --dose_per_frame 1.277 --gainref "$GAIN" --interpolate_shifts
done

echo; echo "===== COMPARISON ====="
python3 "$ROOT/compare.py" "$ROOT/out"
echo "compare exit=$?"

echo; echo "--- load at end ---"; cat /proc/loadavg
echo "STATUS=DONE"
echo "############ END $(date -Is) ############"
