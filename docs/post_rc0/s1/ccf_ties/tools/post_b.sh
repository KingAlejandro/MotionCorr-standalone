#!/bin/bash
# S1.3b post-processing for one family (5x5).
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf
PY=/home/alex/.mc-venv/bin/python3
f=$1; R=$S/runs; A=$S/analysis/b; mkdir -p $A
cd $S
for be in cpu cuda; do
  $PY tools/identity.py $R/$f-p5-prod-$be-none $R/$f-p5-d2-$be-own $R/$f-p5-prod-$be-none $R/$f-p5-d2-$be-negctl \
    > $A/$f-identity-$be.jsonl; echo "identity $f $be rc=$?"
  # Same diagnostic code path as S1.3: the per-frame records must be unchanged.
  cmp -s $R/$f-p5-diag-$be-on/ccf.txt $R/$f-p5-d2-$be-own/ccf.txt; echo "records $f $be d2-own == S1.3 diag-on: rc=$?"
done
$PY tools/pairs.py $f $A/$f-pairs.json > $A/$f-pairs.txt 2>&1; echo "pairs $f rc=$?"
for c in injcpu injcuda; do
  if [ $c = injcpu ]; then a=$f-p5-d2-cpu-own; b=$f-p5-d2-cuda-injcpu; ref=$R/$f-p5-prod-cpu-none; tst=$R/$b
  else a=$f-p5-d2-cpu-injcuda; b=$f-p5-d2-cuda-own; ref=$R/$a; tst=$R/$f-p5-prod-cuda-none; fi
  $PY tools/analyze.py traj $R/$a $R/$b $A/$f-p5-$c-traj.json > $A/$f-p5-$c-traj.txt 2>&1; echo "traj $f $c rc=$?"
  $PY tools/analyze.py maps $S/maps/$a $S/maps/$b $A/$f-p5-$c-traj.json $A/$f-p5-$c-maps.json > $A/$f-p5-$c-maps.txt 2>&1; echo "maps $f $c rc=$?"
  $PY src-prod/tools/compare_motioncorr.py --ref $ref --test $tst --gate backend --json-out $A/$f-p5-$c-backend.json > $A/$f-p5-$c-backend.txt 2>&1
  echo "backend $f $c rc=$? (recorded, not graded) $(grep 'Relative RMSE' $A/$f-p5-$c-backend.txt)"
done
