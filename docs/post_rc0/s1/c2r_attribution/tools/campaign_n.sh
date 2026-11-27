#!/bin/bash
# S1.3c-null census on 4GPUs: every #243 movie of 10216, 12963 and Falcon 3 held on 4GPUs,
# both grids, CUDA diag5 replaying the sweep run (same host/options): off / on (global+DW
# Hermitian projection) / null1 / null2 (size-matched random-sign row offsets).
# First: null-size validation on 10216-00 5x5 with full-frame dumps (off vs null1).
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf; PY=/home/alex/.mc-venv/bin/python3; B=$S/build-diag5-nvcomp/motioncorr
for arm in off null1; do
  l=nv-e10216-00-p5-$arm; mkdir -p $S/full/$l
  envs=(--env MC_DIAG_FULL_DUMP=$S/full/$l --env MC_DIAG_FULL_FRAMES=2,11,21); [ $arm = null1 ] && envs+=(--env MC_DIAG_NULL_ROWS=1)
  $PY $S/tools/run_c.py --gpu --sweep-label e10216-00-p5-F-cuda --label $l --binary $B "${envs[@]}"
done
MOVIES=${MOVIES:-"e10216-00 e10216-01 e10216-02 e10216-03 e10216-04 e10216-05 e10216-06 e12963-00 e12963-01 e12963-02 e12963-03 e12963-04 e12963-05 e12963-06 e12963-07 e12963-08 e12963-09 e10474f3-00 e10474f3-01 e10474f3-02 e10474f3-03"}
for m in $MOVIES; do
  for g in 5 3; do
    sw=$m-p$g-F-cuda
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label n-$m-p$g-off --binary $B
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label n-$m-p$g-on --binary $B --env MC_DIAG_C2R_HERMITIAN_GLOBAL=1 --env MC_DIAG_C2R_HERMITIAN_DW=1
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label n-$m-p$g-null1 --binary $B --env MC_DIAG_NULL_ROWS=1
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label n-$m-p$g-null2 --binary $B --env MC_DIAG_NULL_ROWS=2
  done
done
echo CAMPAIGN-N-DONE
