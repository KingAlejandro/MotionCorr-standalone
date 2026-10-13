#!/bin/bash
# Runs under: flock /tmp/motioncorr-bench.lock taskset -c 96-103
set -uo pipefail
D=/home/alex/mc-mdev-20261013
export PATH=/usr/local/cuda/bin:/home/alex/.mc-venv/bin:$PATH
cd $D
echo "=== VENUE ==="; date -Is; hostname; nproc; grep Cpus_allowed_list /proc/self/status; nvcc --version | tail -1
nvidia-smi --query-gpu=index,uuid --format=csv,noheader
for n in cand nomutex; do
  cmake -S src-$n -B build-$n -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES=80 -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3 > conf-$n.log 2>&1 || { echo "configure $n failed"; exit 1; }
  cmake --build build-$n --parallel 8 > build-$n.log 2>&1 || { echo "build $n failed"; grep -i error build-$n.log | head; exit 1; }
  echo "$n built: $(sha256sum build-$n/motioncorr | cut -c1-16) strings=$(strings build-$n/motioncorr | grep -c 'one worker per device') home=$(grep CMAKE_HOME_DIRECTORY build-$n/CMakeCache.txt)"
done
grep -c NEGCTRL src-nomutex/src/motioncorr_runner.cpp src-cand/src/motioncorr_runner.cpp
/home/alex/.mc-venv/bin/python3 identity.py
echo SERIES_RC=$?
