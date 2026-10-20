#!/bin/bash
# S1.3c #254 arm on 4GPUs: PR #254 head 8b55d5da (projection at all five CUDA C2R sites),
# replaying each #243 sweep run (same host/options). Census movies of 10216/12963/Falcon 3
# held on 4GPUs, both grids; plus all ten 10641 movies (5760x4092) with the #254 arm and
# the diag5 off / null1 / null2 arms (the toggle-on arm is not needed there: no leak).
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf; PY=/home/alex/.mc-venv/bin/python3
P=$S/build-pr254-nvcomp/motioncorr; D=$S/build-diag5-nvcomp/motioncorr
for m in e10216-00 e10216-01 e10216-02 e10216-03 e10216-04 e10216-05 e10216-06 e12963-00 e12963-01 e12963-02 e12963-03 e12963-04 e12963-05 e12963-06 e12963-07 e12963-08 e12963-09 e10474f3-00 e10474f3-01 e10474f3-02 e10474f3-03; do
  for g in 5 3; do $PY $S/tools/run_c.py --gpu --sweep-label $m-p$g-F-cuda --label n-$m-p$g-pr254 --binary $P; done
done
for i in 0 1 2 3 4 5 6 7 8 9; do m=e10641-0$i
  for g in 5 3; do
    sw=$m-p$g-F-cuda
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label n-$m-p$g-pr254 --binary $P
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label n-$m-p$g-off --binary $D
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label n-$m-p$g-null1 --binary $D --env MC_DIAG_NULL_ROWS=1
    $PY $S/tools/run_c.py --gpu --sweep-label $sw --label n-$m-p$g-null2 --binary $D --env MC_DIAG_NULL_ROWS=2
  done
done
echo CAMPAIGN-P-DONE
