#!/bin/bash
# runs under: flock -n LOCK env DC_TIERC_FLOCK_HELD=1 taskset -c 32-47 bash driver.sh WORK
set -u
W=$1; P=$W/pkg/dc_tierc_20261025; INV=$P/INVENTORY.json; PY=/usr/bin/python3
echo "affinity: $(taskset -cp $$)"
$PY -I -B $P/tierc_stage_eval.py fetch-src $W || exit 10
for b in 0 1 2 3 4; do
  $PY -I -B $P/tierc_stage_eval.py stage $W $INV $b || { echo "STAGE FAILED batch $b"; exit 11; }
  $PY -I -B $P/tierc_stage_eval.py evaluate $W $INV $b || { echo "EVAL FAILED batch $b"; exit 12; }
  $PY -I -B $P/tierc_stage_eval.py cleanup $W $INV $b || { echo "CLEANUP FAILED batch $b"; exit 13; }
  df -h /tmp | tail -1
done
echo ALL_BATCHES_DONE
