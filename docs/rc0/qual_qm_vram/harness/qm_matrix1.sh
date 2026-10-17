#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/W-QM
PY=/home/alex/.mc-venv/bin/python3
SPECS=""
for c in L G; do for f in 40 24 16; do SPECS="$SPECS e10441-$c-auto@$f"; done; done
for fam in tutorial e10216 e10474f4; do for c in G L; do for f in 40 24 16; do SPECS="$SPECS $fam-$c-auto@$f"; done; done; done
exec flock /tmp/motioncorr-gpu1-correctness.lock $PY -I qm_batch.py $SPECS
