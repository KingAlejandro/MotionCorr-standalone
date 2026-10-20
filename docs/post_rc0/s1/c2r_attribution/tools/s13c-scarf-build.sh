#!/bin/bash
# S1.3c SCARF build: diag4 (F + diag/s1-ccf-ties 1c82dfcd), CUDA+nvCOMP, Release. CPU partition.
set -u
W=$HOME/mc-s13c
export TMPDIR=/tmp
CU=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH=$CU/bin:$PATH
mkdir -p $W/src-diag4 $W/logs
tar -xzf $W/s13c-diag4.tar.gz -C $W/src-diag4 || exit 2
cmake -S $W/src-diag4 -B $W/build-diag4-cuda -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=$CU/bin/nvcc -DCUDAToolkit_ROOT=$CU \
  -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$HOME/nvcomp-sdk > $W/logs/configure-diag4-cuda.log 2>&1; rc=$?
echo "configure rc=$rc" > $W/logs/build.status; [ $rc = 0 ] || exit $rc
cmake --build $W/build-diag4-cuda -j8 --target motioncorr > $W/logs/build-diag4-cuda.log 2>&1; rc=$?
echo "build rc=$rc $(hostname) $(date -u +%FT%TZ)" >> $W/logs/build.status
grep -h "^CXX_FLAGS\|^CUDA_FLAGS" $W/build-diag4-cuda/CMakeFiles/motioncorr_core.dir/flags.make >> $W/logs/build.status
[ $rc = 0 ] && sha256sum $W/build-diag4-cuda/motioncorr >> $W/logs/build.status
exit $rc
