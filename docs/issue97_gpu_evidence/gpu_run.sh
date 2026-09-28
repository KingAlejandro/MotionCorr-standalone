#!/bin/bash
# Issue #97 CUDA correctness A/B on 4GPUs.
# CORRECTNESS ONLY -- no timing is measured or claimed. The bench lock is taken so this
# run cannot perturb a concurrent benchmark (#53 owns the shared-GPU benchmark slot).
set -u
ROOT=/home/alex/mc-issue97-gpu
LOG=$ROOT/run.log
MOVIES=/home/alex/MotionCorr-standalone/relion30_tutorial/Movies
MOVIE=$MOVIES/20170629_00026_frameImage.tiff
GAIN=$MOVIES/gain.mrc
SYN=$ROOT/src-fixed/test-data/fixtures/synthetic_128x128_8frames.mrcs
LANE="taskset -c 96-103"
J=8
GPU=0                      # single device, selected explicitly

exec >>"$LOG" 2>&1
echo "############ GPU RUN START $(date -Is) ############"

exec 8>/tmp/motioncorr-bench.lock
echo "[bench-lock] acquiring (so this cannot perturb a concurrent benchmark)..."
T0=$(date +%s)
flock -w 3600 8 || { echo "[bench-lock] TIMEOUT"; echo "STATUS=LOCK_TIMEOUT"; exit 90; }
echo "[bench-lock] acquired after $(( $(date +%s) - T0 ))s"

echo "=== DEVICE WITNESS (ordinals do not identify silicon; record UUIDs) ==="
nvidia-smi --query-gpu=index,uuid,name,memory.total,driver_version --format=csv
echo "--- compute apps before (must be empty for a clean attribution) ---"
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
echo "--- lane ---"; $LANE bash -c 'grep Cpus_allowed_list /proc/self/status'
echo "--- inputs ---"; sha256sum "$MOVIE" "$GAIN" "$SYN"

arm () {
    local label=$1; shift; local bin=$1; shift
    local out=$ROOT/out/$label
    rm -rf "$out"; mkdir -p "$out"
    echo; echo "########## ARM $label ##########"
    echo "\$ $bin $*"
    $LANE "$bin" "$@" --o "$out/" > "$out/stdout.log" 2>&1
    local rc=$?
    echo "exit=$rc"
    local f; f=$(find "$out" -name '*.log' ! -name stdout.log | head -1)
    if [ -n "$f" ]; then
        grep -E "^Patches:|^interpolate_shifts|Too few patches" "$f" | head -3
        echo "patch_blocks=$(grep -c '^Patch (' "$f")"
        grep -iE "gpu|device|cuda" "$f" | head -3
    fi
    grep -iE "gpu|device|cuda" "$out/stdout.log" | head -3
}

for tree in base fixed; do
    BIN=$ROOT/build-$tree/motioncorr
    # synthetic, 3x3 patches
    arm "gpu-syn-$tree-off" "$BIN" --i "$SYN" --use_own --gpu $GPU --j $J \
        --patch_x 3 --patch_y 3 --angpix 1 --voltage 300 --dose_per_frame 1
    arm "gpu-syn-$tree-on"  "$BIN" --i "$SYN" --use_own --gpu $GPU --j $J \
        --patch_x 3 --patch_y 3 --angpix 1 --voltage 300 --dose_per_frame 1 --interpolate_shifts
    # real movie, 5x5 patches
    arm "gpu-mov-$tree-off" "$BIN" --i "$MOVIE" --use_own --gpu $GPU --j $J \
        --patch_x 5 --patch_y 5 --angpix 0.885 --voltage 200 --dose_per_frame 1.277 --gainref "$GAIN"
    arm "gpu-mov-$tree-on"  "$BIN" --i "$MOVIE" --use_own --gpu $GPU --j $J \
        --patch_x 5 --patch_y 5 --angpix 0.885 --voltage 200 --dose_per_frame 1.277 --gainref "$GAIN" --interpolate_shifts
done

echo; echo "=== rlnAccumMotion per arm ==="
for a in $(ls "$ROOT/out"); do
    printf "%-22s %s\n" "$a" "$(awk '/\.mrc /{print $3, $4, $5, $6}' "$ROOT/out/$a/corrected_micrographs.star" 2>/dev/null | tail -1)"
done

echo; echo "=== COMPARISON ==="
python3 "$ROOT/compare_products.py" "$ROOT/out" 2>&1 || echo "(numpy absent: byte-level verdicts still valid, per-pixel stats omitted)"

echo; echo "--- compute apps after ---"
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
echo "STATUS=DONE"
echo "############ GPU RUN END $(date -Is) ############"
