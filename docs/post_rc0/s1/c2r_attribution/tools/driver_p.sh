#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-s1ccf || exit 1
until grep -q BUILDS-DONE logs/build_p.out; do sleep 20; done
grep -q "st=0" logs/build_p.out || { echo "build failed" > logs/campaign_p.out; exit 1; }
LANE_GPU=2 bash tools/campaign_p.sh > logs/campaign_p.out 2>&1
echo DRIVER-P-DONE >> logs/campaign_p.out
