#!/bin/bash
# usage: build.sh <srcdir-name> <bdir-name> <cuda:on|off>
set -u
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
src=$S/$1; b=$S/build/$2
mkdir -p $b
if [ "$3" = on ]; then
 X="-DCUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive"
else X=""; fi
taskset -c 80-87 cmake -S $src -B $b -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/mc-env/bin/python3 $X > $b.configure.log 2>&1; echo configure rc=$? >> $b.status
taskset -c 80-87 cmake --build $b -j8 > $b.build.log 2>&1; echo build rc=$? >> $b.status
