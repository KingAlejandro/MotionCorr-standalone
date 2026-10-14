#!/bin/bash
set -eu
export PATH=/workspace/cpu10/deps/usr/bin:$PATH
export LD_LIBRARY_PATH=/workspace/cpu10/deps/usr/lib/x86_64-linux-gnu
export PKG_CONFIG_PATH=/workspace/cpu10/deps/usr/lib/x86_64-linux-gnu/pkgconfig
export CMAKE_PREFIX_PATH=/workspace/cpu10/deps/usr
export OPENBLAS_NUM_THREADS=1
export XDG_CACHE_HOME=/workspace/cpu10/cache
mkdir -p "$XDG_CACHE_HOME"
cmake -S /workspace/cpu10/reference-src -B /workspace/cpu10/build-reference -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON > /workspace/cpu10/configure-reference.log 2>&1
cmake --build /workspace/cpu10/build-reference -j4 > /workspace/cpu10/build-reference.log 2>&1
ctest --test-dir /workspace/cpu10/build-reference --output-on-failure -j1 > /workspace/cpu10/ctest-reference.log 2>&1 || true
cmake -S /workspace/MotionCorr-standalone -B /workspace/cpu10/build-base -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON > /workspace/cpu10/configure-candidate.log 2>&1
cmake --build /workspace/cpu10/build-base -j4 > /workspace/cpu10/build-candidate-tests.log 2>&1
ctest --test-dir /workspace/cpu10/build-base --output-on-failure -j1 > /workspace/cpu10/ctest-candidate.log 2>&1 || true
python3 /workspace/MotionCorr-standalone/tools/run_known_motion_gates.py --binary /workspace/cpu10/bin/candidate --fixtures /workspace/cpu10/known-fixtures --outdir /workspace/cpu10/known-candidate --json /workspace/cpu10/known-candidate.json > /workspace/cpu10/known-candidate.log 2>&1 || true
