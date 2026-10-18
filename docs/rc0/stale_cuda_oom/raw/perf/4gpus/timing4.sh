#!/bin/bash
# The declared design (wd11_pairs.py docstring) on 4GPUs: one window per workload, released between.
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; cd $W
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
TUT=/home/alex/motioncorr-validation-20261011-vm/tutorial-data
G="--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp"
EL="--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --ingest compact"
mkdir -p timing4; python3 -c "import sys; sys.path.insert(0,'$W'); import wd11_pairs; print(wd11_pairs.__doc__)" > timing4/rule.txt
echo "rule recorded $(date -u +%FT%TZ) $(sha256sum timing4/rule.txt | cut -c1-16)"
echo "=== tutG";    bash ./window.sh tutG $TUT $G
echo "=== tutL";    bash ./window.sh tutL $TUT $G --patch_x 5 --patch_y 5
echo "=== e10216L"; bash ./window.sh e10216L $W/perf-e10216 $EL
echo TIMING4_DONE
