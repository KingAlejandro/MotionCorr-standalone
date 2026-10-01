#!/bin/bash
set -euo pipefail
D=/work4/scd/scarf1415/motioncorr/post128-fft-sync-20261001
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
cd "$D"
cmake -S alignment-src -B alignment-cpu-build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF -DUSE_NVCOMP=OFF >alignment-cpu-configure.log 2>&1
taskset -c 0-7 cmake --build alignment-cpu-build --parallel 8 >alignment-cpu-build.log 2>&1
taskset -c 0-7 ctest --test-dir alignment-cpu-build --output-on-failure >alignment-cpu-ctest.log 2>&1
cmake -S alignment-src -B alignment-no-nvcomp-build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=OFF -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME" >alignment-no-nvcomp-configure.log 2>&1
taskset -c 0-7 cmake --build alignment-no-nvcomp-build --parallel 8 >alignment-no-nvcomp-build.log 2>&1
taskset -c 0-7 ctest --test-dir alignment-no-nvcomp-build --output-on-failure >alignment-no-nvcomp-ctest.log 2>&1
touch ALIGNMENT_COMPAT_DONE
