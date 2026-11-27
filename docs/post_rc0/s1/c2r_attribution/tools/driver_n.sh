#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-s1ccf || exit 1
until grep -q BUILDS-DONE logs/build_n.out; do sleep 20; done
grep -q "st=0" logs/build_n.out || { echo "build failed" > logs/campaign_n.out; exit 1; }
LANE_GPU=2 bash tools/campaign_n.sh > logs/campaign_n.out 2>&1
echo DRIVER-N-DONE >> logs/campaign_n.out
