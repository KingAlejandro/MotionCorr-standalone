#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-peakfit
export S13C_ROOT=$S S13C_SWEEP=$S/extra/sweep LANE_GPU=$1
shift
for mv in "$@"; do
 while [ ! -f $S/extra/sweep/runs/$mv-p5-F-cuda/run.json ]; do sleep 5;done
 python3 - "$S" "$mv" <<'PYSETUP'
import json,sys,pathlib
s=pathlib.Path(sys.argv[1]);mv=sys.argv[2];d=json.load(open(s/'extra/sweep/runs'/(mv+'-p5-F-cuda')/'run.json'))
a=d['argv'];a[a.index('--patch_x')+1]='3';a[a.index('--patch_y')+1]='3'
p=s/'extra/sweep/runs'/(mv+'-p3-F-cuda');p.mkdir(exist_ok=True);json.dump(d,open(p/'run.json','w'))
PYSETUP
 for g in 5 3; do
  MC_SOURCE_SHA=6d68e2d6 /usr/bin/python3 $S/tools/run_c.py --sweep-label $mv-p$g-F-cuda --label $mv-p$g-refCPU --binary /mnt/clathrin/alex-motioncorr-rc0/W-QF/build-cpu/motioncorr >> $S/logs/extra-census-$LANE_GPU.log 2>&1
  MC_SOURCE_SHA=8b55d5da /usr/bin/python3 $S/tools/run_c.py --gpu --sweep-label $mv-p$g-F-cuda --label $mv-p$g-parent --binary /mnt/clathrin/alex-motioncorr-s1ccf/build-pr254-nvcomp/motioncorr >> $S/logs/extra-census-$LANE_GPU.log 2>&1
  # Numerical control must match #255 before attribution arms are accepted.
  /usr/bin/python3 $S/tools/check-extra-control.py $mv $g >> $S/logs/extra-census-$LANE_GPU.log 2>&1
  for arm in A0 A1 A2 Nnative1 Nnative2; do
   bin=$S/build-A1/motioncorr; sha=9a834380;args=()
   case $arm in
    A0) bin=$S/build-A0/motioncorr;sha=4837b210;;
    A2) args+=(--env MC_DIAG_ZERO_CCF_DC=1);;
    Nnative1|Nnative2) bin=$S/build-N/motioncorr;sha=7fe2864e;args+=(--env MC_DIAG_FIT_NULL=${arm:7} --env 'MC_DIAG_NULL_RECORD={out}/null-dose.txt');;
   esac
   MC_SOURCE_SHA=$sha /usr/bin/python3 $S/tools/run_c.py --gpu --sweep-label $mv-p$g-F-cuda --label $mv-p$g-$arm --binary $bin --env 'MC_DIAG_CCF={out}/ccf.txt' --env 'MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt' "${args[@]}" >> $S/logs/extra-census-$LANE_GPU.log 2>&1
  done
 done
done
echo DONE >> $S/logs/extra-census-$LANE_GPU.log
