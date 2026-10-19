#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/W-QM
PY=/home/alex/.mc-venv/bin/python3
flock /tmp/motioncorr-gpu1-correctness.lock $PY -I qm_batch.py e10361-L-auto@16 e10361-G-auto@16 mmA-L-auto@16 mmB-L-auto@16 mmA-G-auto@16 mmA-L-auto@24 mmB-L-auto@24
echo M3_DONE
