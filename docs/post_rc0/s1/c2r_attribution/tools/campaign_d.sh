#!/bin/bash
# S1.3c attribution on 4GPUs: CUDA arms replaying #243 sweep runs (same host,
# same options) with the diag4 build: off / global C2R projection / global+DW.
# The CPU reference is the sweep's frozen-F CPU product for the same run.
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf
PY=/home/alex/.mc-venv/bin/python3
B=$S/build-diag4-nvcomp/motioncorr
# 4096^2 screen-positive movies (both grids), 4096^2 negative controls, 10641 positives (non-4096 control)
MOVIES=${MOVIES:-"e10216-00 e10216-01 e10216-02 e10216-03 e10216-06 e12963-00 e12963-01 e12963-02 e12963-03 e12963-04 e12963-05 e12963-07 e10474f3-00 e10474f3-02 e10474f3-03 e10028-00 e10028-02 e10028-06 e10474f4-00 e10474f4-01 e10641-01 e10641-07"}
for m in $MOVIES; do
  for g in 5 3; do
    sw=$m-p$g-F-cuda
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label c-$m-p$g-off --binary $B
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label c-$m-p$g-glob --binary $B --env MC_DIAG_C2R_HERMITIAN_GLOBAL=1
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label c-$m-p$g-globdw --binary $B --env MC_DIAG_C2R_HERMITIAN_GLOBAL=1 --env MC_DIAG_C2R_HERMITIAN_DW=1
  done
done
echo CAMPAIGN-D-DONE
