#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-peakfit
export S13C_ROOT=$S LANE_GPU=$1 MC_SOURCE_SHA=7fe2864e
shift
for mv in "$@"; do
 for g in 5 3; do
  for seed in 1 2; do
   /usr/bin/python3 $S/tools/run_c.py --gpu --sweep-label $mv-p$g-F-cuda --label $mv-p$g-Nnative$seed --binary $S/build-N/motioncorr --env MC_DIAG_FIT_NULL=$seed --env 'MC_DIAG_NULL_RECORD={out}/null-dose.txt' --env 'MC_DIAG_CCF={out}/ccf.txt' --env 'MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt' >> $S/logs/Nnative-$LANE_GPU.log 2>&1
  done
 done
done
echo DONE >> $S/logs/Nnative-$LANE_GPU.log
