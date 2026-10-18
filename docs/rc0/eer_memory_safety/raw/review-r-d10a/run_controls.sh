#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/R-D10a
for spec in "head-cpu 1" "head-asan 1" "head-cpu 2" "head-asan 2" "head-cpu -1" "head-asan -1"; do
  set -- $spec
  python3 scripts/my_controls.py --arm $1 --ups $2 > controls-$1-up$2.log 2>&1; echo "$spec rc=$?" >> controls.done
done
