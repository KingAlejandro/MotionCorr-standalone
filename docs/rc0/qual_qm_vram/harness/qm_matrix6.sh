#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/W-QM
PY=/home/alex/.mc-venv/bin/python3
flock /tmp/motioncorr-gpu1-correctness.lock $PY -I qm_batch.py \
  e10441-L-auto@36.5:scan e10441-L-auto@37:scan e10441-L-auto@37.5:scan e10441-L-auto@38.5:scan \
  e10441-G-auto@36.5:scan e10441-G-auto@37.5:scan \
  e10474f4-L-auto@18.5:scan e10474f4-L-auto@19.5:scan e10474f4-G-auto@18.5:scan \
  e10216-L-auto@7.5:scan e10216-L-auto@8:scan e10216-L-auto@8.75:scan e10216-G-auto@7.5:scan e10216-G-auto@8.25:scan
echo M6_DONE
