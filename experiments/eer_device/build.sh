#!/bin/sh
# Build the experiment out of tree. Usage: build.sh <build-dir> [cpu-list]
# Not part of the main build; needs CUDA >= 12, LibTIFF, FFTW3 (single+double), libpng, libjpeg.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
build=${1:?build dir}
cpus=${2:-}
pin=""; [ -n "$cpus" ] && pin="taskset -c $cpus"
cuda=${CUDA_HOME:-/usr/local/cuda}
$pin cmake -S "$here" -B "$build" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_COMPILER="$cuda/bin/nvcc" -DCUDAToolkit_ROOT="$cuda" -DCMAKE_CUDA_ARCHITECTURES=80
$pin cmake --build "$build" -j 8 --target eer_device_exp eer_device_exp_asan
