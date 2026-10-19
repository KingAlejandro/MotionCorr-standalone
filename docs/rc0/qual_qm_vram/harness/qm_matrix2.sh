#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/W-QM
PY=/home/alex/.mc-venv/bin/python3
SPECS=""
for ing in compact float; do for c in L G; do for f in 40 24 16; do SPECS="$SPECS e10441-$c-$ing@$f"; done; done; done
SPECS="$SPECS mmA-L-auto@16 mmB-L-auto@16 mmA-L-auto@24 mmA-G-auto@16"
flock /tmp/motioncorr-gpu1-correctness.lock $PY -I qm_batch.py $SPECS
B="flock /tmp/motioncorr-gpu1-correctness.lock $PY -I qm_bisect.py"
for c in L G; do
  $B e10441 $c auto resident 24 40
  $B e10441 $c auto completes 16 24
  $B e10474f4 $c auto resident 16 24
  $B e10474f4 $c auto completes 2 16
  $B e10216 $c auto resident 4 16
  $B tutorial $c auto resident 1 16
done
echo ALL_DONE
