#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-peakfit
export S13C_ROOT=$S
export LANE_GPU=$1
shift
export S13C_SWEEP=/mnt/clathrin/alex-motioncorr-s1/sweep
PY=/usr/bin/python3
for mv in "$@"; do
 for grid in 5 3; do
  sw=$mv-p$grid-F-cuda
  for arm in A0 A1 A2 N1 N2; do
   bin=$S/build-A1/motioncorr
   sha=9a834380
   args=()
   case $arm in
    A0) bin=$S/build-A0/motioncorr; sha=4837b210;;
    A2) args+=(--env MC_DIAG_ZERO_CCF_DC=1);;
    N1|N2) bin=$S/build-A0/motioncorr; sha=4837b210; args+=(--env MC_DIAG_FIT_NULL=${arm:1} --env 'MC_DIAG_NULL_RECORD={out}/null-dose.txt');;
   esac
   MC_SOURCE_SHA=$sha $PY $S/tools/run_c.py --gpu --sweep-label "$sw" --label "$mv-p$grid-$arm" --binary "$bin" --env 'MC_DIAG_CCF={out}/ccf.txt' --env 'MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt' "${args[@]}" >> "$S/logs/campaign-$LANE_GPU.log" 2>&1
  done
 done
done
echo DONE >> "$S/logs/campaign-$LANE_GPU.log"
