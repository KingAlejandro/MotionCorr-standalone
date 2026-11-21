#!/bin/bash
set -euo pipefail
W=/tmp/motioncorr-214
export PATH=/home/ubuntu/.mc-venv/bin:$PATH
cd "$W"
lscpu > logs/hardware.txt
for arm in baseline src; do
 taskset -c 8-15 cmake -S "$W/$arm" -B "$W/build-$arm" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF > "logs/configure-$arm.log" 2>&1
 taskset -c 8-15 cmake --build "$W/build-$arm" -j8 > "logs/build-$arm.log" 2>&1
 sha256sum "$W/build-$arm/motioncorr"
 done
find /home/ubuntu/mc-corpus-186 -maxdepth 4 -type f | head -40 || true
echo BUILDS_DONE
