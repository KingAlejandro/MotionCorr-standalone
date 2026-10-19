#!/bin/bash
set -u
W=/mnt/clathrin/alex-motioncorr-rc0/W-QM
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
PY=/home/alex/.mc-venv/bin/python3
NVC=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
cd $W/src || exit 90
[ "$(git rev-parse HEAD)" = 483e881d9a6a352dba3268dac0f8c729364860b5 ] || exit 91
taskset -c 104-111 cmake -S $W/src -B $W/build-nvcomp -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DPython3_EXECUTABLE=$PY -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NVC > $W/logs/configure.log 2>&1
echo configure rc=$?
grep -E 'CMAKE_HOME_DIRECTORY|CMAKE_BUILD_TYPE' $W/build-nvcomp/CMakeCache.txt
taskset -c 104-111 cmake --build $W/build-nvcomp -j8 > $W/logs/build.log 2>&1
echo build rc=$?
sha256sum $W/build-nvcomp/motioncorr
