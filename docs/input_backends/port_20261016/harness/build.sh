#!/bin/bash
# usage: build.sh <name> <srcdir> <cuda:0|1>
set -u
D=/mnt/clathrin/alex-motioncorr-rc0/W-TIFF
name=$1; src=$2; cuda=$3
export PATH=/home/alex/mc-env/bin:/usr/local/cuda-12.8/bin:$PATH
rm -rf $D/build-$name
if [ "$cuda" = 1 ]; then
  EXTRA="-DCUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive"
else EXTRA=""; fi
cmake -S $src -B $D/build-$name -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/mc-env/bin/python3 $EXTRA > $D/configure-$name.log 2>&1; echo "configure rc=$?" > $D/build-$name.rc
cmake --build $D/build-$name -j8 > $D/build-$name.log 2>&1; echo "build rc=$?" >> $D/build-$name.rc
