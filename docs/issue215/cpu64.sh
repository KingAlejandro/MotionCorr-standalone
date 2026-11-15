#!/bin/bash
set -euo pipefail
W=/tmp/motioncorr-215-cpu64
export PATH=$HOME/.mc-venv/bin:$PATH OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 CUDA_VISIBLE_DEVICES=
cd "$W/src"
exec >"$W/validation.log" 2>&1
trap 'echo DRIVER_EXIT=$? $(date -u +%FT%TZ)' EXIT
hostname; uname -a; date -u +%FT%TZ
git rev-parse HEAD
git status --porcelain
echo 'taskset -c 24-31; OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1; no timing lock (correctness only)'
lscpu | head -18
gcc --version | head -1
python3 -c 'import numpy,sys; print(sys.version); print(numpy.__version__)'
taskset -c 24-31 cmake -S . -B "$W/build-cpu" -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DUSE_NVCOMP=OFF -DBUILD_TESTING=ON -DPython3_EXECUTABLE="$HOME/.mc-venv/bin/python3" > "$W/config.log" 2>&1
echo CONFIG_RC=0
taskset -c 24-31 cmake --build "$W/build-cpu" -j8 > "$W/build.log" 2>&1
echo BUILD_RC=0
(cd tools/profiling && python3 -c 'from lib.provenance import compilers_running; print("compilers before CTest:",compilers_running())')
taskset -c 24-31 ctest --test-dir "$W/build-cpu" --output-on-failure -j1 --output-junit "$W/ctest.xml" > "$W/ctest.log" 2>&1
echo CTEST_RC=0
sha256sum "$W/build-cpu/motioncorr"
