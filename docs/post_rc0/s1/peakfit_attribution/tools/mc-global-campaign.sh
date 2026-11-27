#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-peakfit
export S13C_ROOT=$S LANE_GPU=3
PY=/usr/bin/python3
for mv in "$@"; do
 for arm in cpu A0 A1; do
  if [[ $arm = cpu && ( $mv = e10216-00 || $mv = e12963-00 ) ]]; then continue; fi
  args=(--gpu); bin=$S/build-A1/motioncorr; sha=9a834380
  if [ "$arm" != A1 ]; then bin=$S/build-A0/motioncorr;sha=4837b210;fi
  if [ "$arm" = cpu ]; then args=();fi
  MC_SOURCE_SHA=$sha $PY $S/tools/run_c.py --sweep-label $mv-p5-F-cuda --label $mv-G-$arm --binary $bin --config G --save-nodw "${args[@]}" --env 'MC_DIAG_CCF={out}/ccf.txt' --env 'MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt' >> $S/logs/global-campaign.log 2>&1
 done
done
for mv in e10216-00 e12963-00 e10474f3-00; do
 for grid in 5 3; do
  for arm in cpu cpuDC; do
   extra=();if [ "$arm" = cpuDC ]; then extra=(--env MC_DIAG_ZERO_CCF_DC=1);fi
   MC_SOURCE_SHA=4837b210 $PY $S/tools/run_c.py --sweep-label $mv-p$grid-F-cuda --label $mv-p$grid-$arm --binary $S/build-A0/motioncorr --env 'MC_DIAG_CCF={out}/ccf.txt' --env 'MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt' "${extra[@]}" >> $S/logs/cpu-control-campaign.log 2>&1
  done
 done
done
echo DONE >> $S/logs/global-campaign.log
