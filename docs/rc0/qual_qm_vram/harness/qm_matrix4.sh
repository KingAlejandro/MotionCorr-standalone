#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/W-QM
PY=/home/alex/.mc-venv/bin/python3
B="flock /tmp/motioncorr-gpu1-correctness.lock $PY -I qm_bisect.py"
$B e10216 L auto completes 1 8.5
$B tutorial L auto completes 1 3
$B e10216 G auto completes 1 8.5
$B tutorial G auto resident 1 16
$B tutorial G auto completes 1 3
echo M4_DONE
