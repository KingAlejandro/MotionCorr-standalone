#!/bin/bash
# usage: campaign.sh <name> <baseName> <baseBin> <baseSrc> <candName> <candBin> <candSrc>
set -u
name=$1; bn=$2; bb=$3; bs=$4; cn=$5; cb=$6; cs=$7
R=/home/alex/mc-rc; W=$R/camp/$name
mkdir -p $R/camp; rm -rf $W
python3 $R/src-kit/tools/profiling/mcprof.py compare $bn=$bb $cn=$cb \
  --data /home/alex/mc-perf-20261001/data --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 \
  --runner-cpus 120-121 --lane-wait 600 --settle-timeout 600 --pairs 12 --max-rounds 20 \
  --profile-pass 3 --trace-pass 2 --work $W --source $bn=$bs --source $cn=$cs -- \
  --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 \
  --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp > $R/camp/$name.log 2>&1
echo "$name rc=$?" >> $R/camp/status.txt
du -sh $W >> $R/camp/status.txt
