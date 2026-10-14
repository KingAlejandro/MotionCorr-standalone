#!/bin/bash
set -eu
python3 /workspace/cpu10/build_probe.py > /workspace/cpu10/build-probe-waits.log 2>&1
for j in 1 4; do
 mask=0
 if [ "$j" = 4 ]; then mask=0-3; fi
 OMP_NUM_THREADS=$j OMP_PROC_BIND=close OMP_PLACES=cores OMP_DYNAMIC=false OPENBLAS_NUM_THREADS=1 taskset -c "$mask" /workspace/cpu10/bin/probe-waits --i /workspace/cpu10/data/tutorial.tiff --o /workspace/cpu10/probe-waits-j$j --use_own --j "$j" --angpix 0.885 --voltage 300 --gainref /workspace/cpu10/data/gain.mrc --patch_x 5 --patch_y 5 --bfactor 150 --dose_weighting --dose_per_frame 1.277 --save_noDW --even_odd_split --profile /workspace/cpu10/probe-waits-j$j.jsonl > /workspace/cpu10/probe-waits-j$j.log 2>&1
done
