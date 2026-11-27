#!/bin/bash
# S1.3c size control: full-frame dumps on 10641-01 (5760x4092), CUDA diag4 off vs global projection.
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf; PY=/home/alex/.mc-venv/bin/python3; B=$S/build-diag4-nvcomp/motioncorr
for arm in off glob; do
  l=f-e10641-01-p5-$arm; mkdir -p $S/full/$l
  envs=(--env MC_DIAG_FULL_DUMP=$S/full/$l --env MC_DIAG_FULL_FRAMES=2,11,21)
  [ $arm = glob ] && envs+=(--env MC_DIAG_C2R_HERMITIAN_GLOBAL=1)
  $PY $S/tools/run_c.py --gpu --sweep-label e10641-01-p5-F-cuda --label $l --binary $B "${envs[@]}"
done
