#!/bin/bash
# S1.3 campaign: per family, config L, production and diagnostic builds on both
# backends. "off" = diagnostic build, no diagnostic env. "on" = per-frame records
# (MC_DIAG_CCF) plus raw CCF map/input dumps for all 25 patches and global.
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf
PY=/home/alex/.mc-venv/bin/python3
# case = family:patch grid; 10216 3x3 first (#243: S1 without an acceptance flip).
CASES=${CASES:-"e10216:3 e10216:5 e12963:5 e10474f3:5 e10641b:5"}
run() { fam=$1 build=$2 be=$3 mode=$4 np=$5
  label=$fam-p$np-$build-$be-$mode
  ALL="g"; for y in $(seq 1 $np); do for x in $(seq 1 $np); do ALL="$ALL;$y,$x"; done; done
  [ -f $S/runs/$label/run.json ] && { echo "skip $label"; return; }
  args=(--family $fam --patches $np --label $label --binary $S/build-$build-$( [ $be = cuda ] && echo nvcomp || echo cpu )/motioncorr)
  [ $be = cuda ] && args+=(--gpu)
  if [ $mode = on ]; then
    rm -rf $S/maps/$label $S/runs/$label  # append-mode logs: start clean
    mkdir -p $S/maps/$label $S/runs/$label
    args+=(--env MC_DIAG_CCF=$S/runs/$label/ccf.txt --env MC_DIAG_MAPS=$S/maps/$label --env "MC_DIAG_MAP_PATCHES=$ALL")
  fi
  $PY $S/tools/run.py "${args[@]}"
}
for c in $CASES; do
  fam=${c%:*} np=${c#*:}
  for be in ${BACKENDS:-cpu cuda}; do
    run $fam prod $be none $np
    run $fam diag $be off $np
    run $fam diag $be on $np
  done
done
echo CAMPAIGN-DONE
