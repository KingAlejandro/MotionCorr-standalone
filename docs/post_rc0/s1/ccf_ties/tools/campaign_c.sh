#!/bin/bash
# S1.3b full-frame dumps (diag3): equal global trajectory on both backends
# (CPU with CUDA's trajectory injected, CUDA with its own), frames 2, 11, 21.
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf
PY=/home/alex/.mc-venv/bin/python3
for fam in ${FAMS:-e10216 e12963}; do
  for spec in "cpu injcuda MC_DIAG_GLOBAL_SHIFTS=$S/shifts/$fam-cuda.txt" "cuda own MC_DIAG_GLOBAL_SHIFTS=$S/shifts/$fam-cuda.txt"; do
    set -- $spec; be=$1 mode=$2 env=$3
    label=$fam-p5-d3-$be-$mode-full
    [ -f $S/runs/$label/run.json ] && { echo "skip $label"; continue; }
    rm -rf $S/runs/$label $S/full/$label; mkdir -p $S/runs/$label $S/full/$label
    args=(--family $fam --patches 5 --label $label --binary $S/build-diag3-$( [ $be = cuda ] && echo nvcomp || echo cpu )/motioncorr
          --env "$env" --env MC_DIAG_FULL_DUMP=$S/full/$label --env MC_DIAG_FULL_FRAMES=2,11,21)
    [ $be = cuda ] && args+=(--gpu)
    $PY $S/tools/run.py "${args[@]}"
  done
done
echo CAMPAIGN-C-DONE
