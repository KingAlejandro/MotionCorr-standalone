#!/bin/bash
# S1.3c post-processing for parts 2 and 4 (4GPUs scratch root).
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf; PY=/home/alex/.mc-venv/bin/python3; R=$S/runs; A=$S/analysis/c; mkdir -p $A
cd $S
for f in e10216 e12963; do
  $PY tools/part2.py $f $A/$f-part2.json; echo "part2 $f rc=$?"
  for m in injcpu-herm own-herm; do
    c=$f-p5-$m
    $PY tools/analyze.py traj $R/$f-p5-d2-cpu-own $R/$f-p5-d4-cuda-$m $A/$c-traj.json > $A/$c-traj.txt 2>&1; echo "traj $c rc=$?"
    $PY tools/analyze.py maps $S/maps/$f-p5-d2-cpu-own $S/maps/$f-p5-d4-cuda-$m $A/$c-traj.json $A/$c-maps.json > $A/$c-maps.txt 2>&1; echo "maps $c rc=$?"
    $PY src-prod/tools/compare_motioncorr.py --ref $R/$f-p5-prod-cpu-none --test $R/$f-p5-d4-cuda-$m --gate backend --json-out $A/$c-backend.json > $A/$c-backend.txt 2>&1
    echo "backend $c $(grep 'Relative RMSE' $A/$c-backend.txt)"
  done
done
$PY tools/summarize.py $A e10216-p5-injcpu-herm e10216-p5-own-herm e12963-p5-injcpu-herm e12963-p5-own-herm > $A/summary_c.json
$PY tools/counts.py $A/summary_c.json > $A/counts_c.json 2> $A/first_separation_table_c.md
# Part 4: products, config G with --save_noDW (DW sum = main MRC, noDW sum = *_noDW.mrc).
for m in e10216-00 e12963-00; do
  ref=$R/e-$m-G-cpu
  for arm in off glob dw globdw; do
    t=$R/e-$m-G-$arm
    dw=$($PY src-prod/tools/compare_motioncorr.py --ref-mrc $(ls $ref/Movies/*.mrc | grep -v _noDW) --test-mrc $(ls $t/Movies/*.mrc | grep -v _noDW) --gate backend 2>&1 | grep 'Relative RMSE' | awk '{print $3}')
    nodw=$($PY src-prod/tools/compare_motioncorr.py --ref-mrc $(ls $ref/Movies/*_noDW.mrc) --test-mrc $(ls $t/Movies/*_noDW.mrc) --gate backend 2>&1 | grep 'Relative RMSE' | awk '{print $3}')
    echo "$m $arm DW_rel_rmse=$dw noDW_rel_rmse=$nodw"
  done
done > $A/part4.txt
cat $A/part4.txt
