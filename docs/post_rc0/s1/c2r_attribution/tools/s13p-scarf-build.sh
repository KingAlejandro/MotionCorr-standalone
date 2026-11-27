#!/bin/bash
# S1.3c SCARF build: pr254 (PR #254 head 8b55d5da), CUDA+nvCOMP, Release. CPU partition.
set -u
W=$HOME/mc-s13c
export TMPDIR=/tmp
CU=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH=$CU/bin:$PATH
mkdir -p $W/src-pr254 $W/logs
tar -xzf $W/s13c-pr254.tar.gz -C $W/src-pr254 || exit 2
cmake -S $W/src-pr254 -B $W/build-pr254-cuda -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=$CU/bin/nvcc -DCUDAToolkit_ROOT=$CU \
  -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$HOME/nvcomp-sdk > $W/logs/configure-pr254-cuda.log 2>&1; rc=$?
echo "configure rc=$rc" > $W/logs/build.status; [ $rc = 0 ] || exit $rc
cmake --build $W/build-pr254-cuda -j8 --target motioncorr > $W/logs/build-pr254-cuda.log 2>&1; rc=$?
echo "build rc=$rc $(hostname) $(date -u +%FT%TZ)" >> $W/logs/build.status
grep -h "^CXX_FLAGS\|^CUDA_FLAGS" $W/build-pr254-cuda/CMakeFiles/motioncorr_core.dir/flags.make >> $W/logs/build.status
[ $rc = 0 ] && sha256sum $W/build-pr254-cuda/motioncorr >> $W/logs/build.status
exit $rc
