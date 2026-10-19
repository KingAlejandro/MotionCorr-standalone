#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/W-QM
PY=/home/alex/.mc-venv/bin/python3
export PATH=/usr/local/cuda-12.8/bin:$PATH
taskset -c 104-111 nvcc -arch=sm_80 -o stale_repro qm_stale.cu
flock /tmp/motioncorr-gpu1-correctness.lock bash -c 'CUDA_VISIBLE_DEVICES=1 taskset -c 104-111 ./stale_repro' > logs/stale_repro.out 2>&1
flock /tmp/motioncorr-gpu1-correctness.lock $PY -I qm_batch.py mmC-L-auto@16 mmC-L-auto@24
echo M5_DONE
