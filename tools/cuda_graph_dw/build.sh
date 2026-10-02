#!/bin/sh
# Build the isolated graph probe. Not wired into the product CMake build.
set -e
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
out=${1:-$here/build}
mkdir -p "$out"
python3 "$here/extract_kernels.py" "$repo/src/acc/cuda/cuda_realspace_dw.cu" \
        "$out/dw_kernels_generated.cuh"
nvcc -O3 -std=c++17 -arch=sm_80 -lineinfo \
     -I"$out" -o "$out/graph_dw_probe" "$here/graph_dw_probe.cu" -lcufft
echo "built $out/graph_dw_probe"
