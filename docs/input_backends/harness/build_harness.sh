#!/bin/bash
# Compile dump_native_samples against an already-built tree, out of tree.
#
# CMakeLists.txt is not touched and the product binary is not relinked, so the
# compiled paths of motioncorr itself stay exactly as they are at the code head.
# The harness links the same libmotioncorr_core.a the product binary links, and
# is compiled with the same flags CMake gives that library, so the readTIFF it
# exercises is the one under test.
#
# Usage: build_harness.sh <source-tree> <build-dir> <output-binary>
set -euo pipefail

SRC=$1
BUILD=$2
OUT=$3
HERE=$(cd "$(dirname "$0")" && pwd)

test -f "$BUILD/libmotioncorr_core.a" || { echo "no libmotioncorr_core.a in $BUILD"; exit 1; }

# A CUDA-enabled core defines _CUDA_ENABLED publicly and pulls in the runtime,
# so the harness has to match that configuration or the headers disagree.
EXTRA_DEFS=()
EXTRA_LIBS=()
if grep -q "_CUDA_ENABLED" "$BUILD/CMakeCache.txt" 2>/dev/null || \
   nm -C "$BUILD/libmotioncorr_core.a" 2>/dev/null | grep -q "cudaMalloc"; then
    EXTRA_DEFS+=(-D_CUDA_ENABLED)
    EXTRA_LIBS+=(-L"${CUDA_HOME:-/usr/local/cuda}/lib64" -lcudart -lcufft)
    echo "linking harness against CUDA runtime"
fi

g++ -std=c++17 -O2 -fopenmp \
    -DHAVE_TIFF -DHAVE_PNG -DHAVE_JPEG "${EXTRA_DEFS[@]}" \
    -I"$SRC" \
    "$HERE/dump_native_samples.cpp" \
    -o "$OUT" \
    "$BUILD/libmotioncorr_core.a" \
    $(pkg-config --libs fftw3 fftw3f) \
    -ltiff -lpng -ljpeg -lz -lpthread "${EXTRA_LIBS[@]}"

echo "built $OUT"
sha256sum "$OUT"
