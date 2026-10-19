#!/bin/bash
# S1.3 post-processing for one case: identity (instrumentation neutrality),
# CPU-vs-CUDA backend comparison of production arms (recorded, not graded),
# per-frame trajectory analysis and map analysis.
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf
PY=/home/alex/.mc-venv/bin/python3
c=$1   # e.g. e10216-p3
mkdir -p $S/analysis
R=$S/runs
for be in cpu cuda; do
  $PY $S/tools/identity.py $R/$c-prod-$be-none $R/$c-diag-$be-off $R/$c-prod-$be-none $R/$c-diag-$be-on \
    > $S/analysis/$c-identity-$be.jsonl; echo "identity $c $be rc=$?"
done
$PY $S/src-prod/tools/compare_motioncorr.py --ref $R/$c-prod-cpu-none --test $R/$c-prod-cuda-none --gate backend \
  --json-out $S/analysis/$c-backend.json > $S/analysis/$c-backend.txt 2>&1; echo "backend-gate $c rc=$? (recorded, not graded)"
$PY $S/tools/analyze.py traj $R/$c-diag-cpu-on $R/$c-diag-cuda-on $S/analysis/$c-traj.json > $S/analysis/$c-traj.txt 2>&1; echo "traj $c rc=$?"
$PY $S/tools/analyze.py maps $S/maps/$c-diag-cpu-on $S/maps/$c-diag-cuda-on $S/analysis/$c-traj.json $S/analysis/$c-maps.json > $S/analysis/$c-maps.txt 2>&1; echo "maps $c rc=$?"
$PY $S/tools/fitattr.py $R/$c-prod-cpu-none $R/$c-prod-cuda-none $S/analysis/$c-fitattr.json > $S/analysis/$c-fitattr.txt 2>&1; echo "fitattr $c rc=$?"
