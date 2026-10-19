#!/bin/bash
# Replacement AA nulls for tutG and tutL (their interleaved nulls used the defective driver: the A-prime
# output path broke the unquoted gs call). Fixed driver, --null-only, one window each.
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; cd $W
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
until grep -q TIMING4_DONE timing4.out; do sleep 20; done
TUT=/home/alex/motioncorr-validation-20261011-vm/tutorial-data
G="--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp"
echo "=== tutG-null"; EXTRA_DRIVER=--null-only bash ./window.sh tutG-null $TUT $G
echo "=== tutL-null"; EXTRA_DRIVER=--null-only bash ./window.sh tutL-null $TUT $G --patch_x 5 --patch_y 5
echo TIMING4B_DONE
