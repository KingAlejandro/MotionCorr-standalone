#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-peakfit
export S13C_ROOT=$S LANE_GPU=0
for mv in e10216-00 e12963-00 e10474f3-00; do
 for g in 5 3; do
  for arm in A1plain Noff; do
   bin=$S/build-A1/motioncorr;sha=9a834380;parent=A1
   if [ $arm = Noff ]; then bin=$S/build-N/motioncorr;sha=7fe2864e;parent=A0;fi
   MC_SOURCE_SHA=$sha /usr/bin/python3 $S/tools/run_c.py --gpu --sweep-label $mv-p$g-F-cuda --label $mv-p$g-$arm --binary $bin >> $S/logs/neutrality-campaign.log 2>&1
   /usr/bin/python3 $S/tools/identity.py $S/runs/$mv-p$g-$parent $S/runs/$mv-p$g-$arm >> $S/logs/neutrality-results.jsonl
  done
 done
done
echo DONE >> $S/logs/neutrality-campaign.log
