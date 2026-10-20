#!/bin/bash
# S1.3c 4GPUs driver: wait for the diag4 build, then parts 2+4 (campaign_e), then part 3 (campaign_d).
cd /mnt/clathrin/alex-motioncorr-s1ccf || exit 1
until grep -q BUILDS-DONE logs/build_d.out; do sleep 20; done
grep -q "st=0" logs/build_d.out || { echo "build failed" > logs/driver_cde.out; exit 1; }
export LANE_GPU=2
bash tools/campaign_e.sh > logs/campaign_e.out 2>&1
bash tools/campaign_d.sh > logs/campaign_d.out 2>&1
echo DRIVER-DONE >> logs/campaign_d.out
