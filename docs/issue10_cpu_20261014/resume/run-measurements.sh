#!/bin/bash
set -eu
export PATH=/workspace/scratch/4d99fce6c5db/build-deps/usr/bin:$PATH
export LD_LIBRARY_PATH=/workspace/scratch/4d99fce6c5db/build-deps/usr/lib/x86_64-linux-gnu
export OPENBLAS_NUM_THREADS=1
root=/workspace/scratch/28038873ca11
repo=$root/MotionCorr-standalone
py=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3
for j in 1 4; do
  mask=0
  if [ "$j" = 4 ]; then mask=0-3; fi
  OMP_NUM_THREADS=$j OMP_PROC_BIND=close OMP_PLACES=cores OMP_DYNAMIC=false flock /tmp/motioncorr-bench.lock taskset -c "$mask" "$root/probe-waits" --i "$root/data/tutorial.tiff" --o "$root/probe-j$j" --use_own --j "$j" --angpix 0.885 --voltage 300 --gainref "$root/data/gain.mrc" --patch_x 5 --patch_y 5 --bfactor 150 --dose_weighting --dose_per_frame 1.277 --save_noDW --even_odd_split --profile "$root/probe-j$j.jsonl" > "$root/probe-j$j.log" 2>&1
done
for j in 4; do
  "$py" "$repo/docs/issue10_cpu_20261014/run_unprofiled.py" --base "$root/build-reference/motioncorr" --candidate "$root/build-candidate/motioncorr" --data "$root/data" --out "$root/unprofiled-tutorial-patch-j$j" --repeats 6 --geometry tutorial --patch 5 --threads "$j"
done
for patch in 1 5; do
 for j in 1 4; do
  "$py" "$repo/docs/issue10_cpu_20261014/run_unprofiled.py" --base "$root/build-reference/motioncorr" --candidate "$root/build-candidate/motioncorr" --data "$root/data" --out "$root/unprofiled-synthetic-p$patch-j$j" --repeats 3 --geometry synthetic --patch "$patch" --threads "$j"
 done
done
