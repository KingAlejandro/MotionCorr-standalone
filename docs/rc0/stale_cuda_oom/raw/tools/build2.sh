#!/bin/bash
# usage: build.sh <srcdir> <builddir> <cpu|cuda|nvcomp>
set -u
SRC=$1; B=$2; KIND=$3; CPUS=24-39
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
PY=/home/alex/.mc-venv/bin/python3
NVC=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
CUDA_ARGS="-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8"
case $KIND in
 cpu) EXTRA="-DCUDA=OFF";;
 cuda) EXTRA="$CUDA_ARGS -DUSE_NVCOMP=OFF";;
 nvcomp) EXTRA="$CUDA_ARGS -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NVC";;
esac
echo "src=$(git -C $SRC rev-parse HEAD) dirty=$(git -C $SRC status --porcelain | wc -l) kind=$KIND start=$(date -u +%FT%TZ)"
taskset -c $CPUS cmake -S $SRC -B $B -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=$PY $EXTRA > $B.configure.log 2>&1 || { echo configure-fail; exit 1; }
grep CMAKE_HOME_DIRECTORY $B/CMakeCache.txt
taskset -c $CPUS cmake --build $B -j16 > $B.build.log 2>&1; rc=$?
echo "build rc=$rc end=$(date -u +%FT%TZ)"
[ $rc -eq 0 ] && sha256sum $B/motioncorr && grep -h -- "-O3" $B/CMakeFiles/motioncorr.dir/flags.make | head -1
exit $rc
