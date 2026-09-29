#!/bin/bash
# Issue #85: matched full-application pairs, identical MotionCorr binary,
# two LibTIFF 4.5.1 builds differing only in libdeflate support.
# Budget: taskset -c 0-31 (measurement cpuset), --j 8 (= n_io_threads 8).
set -u
WD=/home/ubuntu/mc-i85-codec-20260929
cd "$WD/run"
OUT="$WD/results"; mkdir -p "$OUT"
BIN="$WD/build-sys/motioncorr"
COMMON="--i movies24.star --use_own --j 8 --seed 1 --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150"

# Warm the page cache identically for every arm before any timed run.
cat Movies/*.tiff Movies/gain.mrc > /dev/null 2>&1
cat Movies/*.tiff Movies/gain.mrc > /dev/null 2>&1

run_one() {
  local arm=$1 mode=$2 rep=$3
  local tag="${mode}_${arm}_rep${rep}"
  local gainopt=""
  [ "$mode" = gain ] && gainopt="--gainref Movies/gain.mrc"
  rm -rf "$OUT/$tag"
  /usr/bin/time -v -o "$OUT/$tag.time" \
    taskset -c 0-31 env LD_LIBRARY_PATH="$WD/tiff-$arm/lib" \
    "$BIN" $COMMON $gainopt --o "$OUT/$tag" > "$OUT/$tag.stdout" 2>&1
  local rc=$?
  echo "$tag rc=$rc wall=$(grep -o 'wall clock.*' "$OUT/$tag.time" | awk '{print $NF}') maxrss_kb=$(awk '/Maximum resident/{print $NF}' "$OUT/$tag.time") movies=$(find "$OUT/$tag" -name '*_frameImage.mrc' | wc -l)"
}

for rep in 1 2 3; do
  if [ $((rep % 2)) -eq 1 ]; then order="ld zlib"; else order="zlib ld"; fi
  for arm in $order; do run_one "$arm" gain "$rep"; done
done
for rep in 1 2; do
  if [ $((rep % 2)) -eq 1 ]; then order="zlib ld"; else order="ld zlib"; fi
  for arm in $order; do run_one "$arm" nogain "$rep"; done
done
echo BENCH_DONE
