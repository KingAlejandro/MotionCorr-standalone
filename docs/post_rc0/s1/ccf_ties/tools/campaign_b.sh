#!/bin/bash
# S1.3b campaign (global-trajectory override), 5x5, diag2 builds, lane from LANE_GPU.
#   own     : own trajectory written to shifts/<fam>-<be>.txt; records + patch map dumps
#   negctl  : own trajectory injected back (must be byte-identical to production)
#   inj     : the other backend's trajectory injected; records + patch map dumps
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf
PY=/home/alex/.mc-venv/bin/python3
FAMS=${FAMS:-"e10216 e12963"}
mkdir -p $S/shifts
run() { fam=$1 be=$2 mode=$3; shift 3
  label=$fam-p5-d2-$be-$mode
  [ -f $S/runs/$label/run.json ] && { echo "skip $label"; return; }
  rm -rf $S/maps/$label $S/runs/$label; mkdir -p $S/runs/$label $S/maps/$label  # append-mode logs: start clean
  args=(--family $fam --patches 5 --label $label --binary $S/build-diag2-$( [ $be = cuda ] && echo nvcomp || echo cpu )/motioncorr)
  [ $be = cuda ] && args+=(--gpu)
  for e in "$@"; do args+=(--env "$e"); done
  $PY $S/tools/run.py "${args[@]}"
}
ALL=""; for y in 1 2 3 4 5; do for x in 1 2 3 4 5; do ALL="$ALL;$y,$x"; done; done; ALL=${ALL#;}
for fam in $FAMS; do
  for be in cpu cuda; do
    l=$fam-p5-d2-$be-own
    run $fam $be own MC_DIAG_GLOBAL_SHIFTS_OUT=$S/shifts/$fam-$be.txt MC_DIAG_CCF=$S/runs/$l/ccf.txt MC_DIAG_MAPS=$S/maps/$l "MC_DIAG_MAP_PATCHES=$ALL"
  done
  for be in cpu cuda; do
    run $fam $be negctl MC_DIAG_GLOBAL_SHIFTS=$S/shifts/$fam-$be.txt
  done
  for be in cpu cuda; do
    other=$( [ $be = cpu ] && echo cuda || echo cpu )
    l=$fam-p5-d2-$be-inj$other
    run $fam $be inj$other MC_DIAG_GLOBAL_SHIFTS=$S/shifts/$fam-$other.txt MC_DIAG_CCF=$S/runs/$l/ccf.txt MC_DIAG_MAPS=$S/maps/$l "MC_DIAG_MAP_PATCHES=$ALL"
  done
done
echo CAMPAIGN-B-DONE
