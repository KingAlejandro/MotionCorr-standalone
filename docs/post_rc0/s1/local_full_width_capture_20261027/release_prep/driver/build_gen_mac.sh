#!/bin/bash
# Mac-only helper for the witness tests: compile the generator against an exact-archive build tree (default: the reviewed r2 build of f473fbc9).
set -eu
W=${1:-/tmp/mc-capext-20261027-r2}; OUT=${2:-/tmp/mc-capwit-20261027/gen_fw_capture}
mkdir -p $(dirname $OUT)
FL="-O3 -DNDEBUG -std=gnu++17 -arch arm64 -Xpreprocessor -fopenmp -DMC_EXPERIMENT_CCF_DC -I/opt/homebrew/opt/libomp/include -I$W/src -isystem /opt/homebrew/Cellar/fftw/3.3.11/include -isystem /opt/homebrew/include"
LIBS="$W/build/libmotioncorr_core.a /opt/homebrew/Cellar/fftw/3.3.11/lib/libfftw3.dylib /opt/homebrew/Cellar/fftw/3.3.11/lib/libfftw3f.dylib /opt/homebrew/opt/libomp/lib/libomp.dylib /opt/homebrew/lib/libtiff.dylib /opt/homebrew/lib/libpng.dylib /opt/homebrew/lib/libjpeg.dylib -lz"
c++ $FL "$(dirname "$0")/gen_fw_capture.cpp" -o $OUT $LIBS
echo built $OUT
