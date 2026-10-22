#!/bin/bash
# usage: c1_build.sh SRCDIR BUILDDIR "TARGETS|all" [cmake args...]   Release, -j2, CPUs 8-9, nonblocking shared build lock.
set -u
source "$(dirname "$0")/c1_env.sh" || exit 1
src=$1; b=$2; targets=$3; shift 3
exec 8>"$C1_BUILD_LOCK"; flock -n 8 || { echo "build lock contended; stopping, no retry"; exit 5; }
CUDA_ARGS="-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8"
case "${CFG:-}" in cpu) X="-DCUDA=OFF";; cuda) X="$CUDA_ARGS -DUSE_NVCOMP=OFF";; nvcomp) X="$CUDA_ARGS -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$C1_NVCOMP";; *) echo "CFG=cpu|cuda|nvcomp required"; exit 2;; esac
taskset -c $C1_CPUS cmake -S "$src" -B "$b" -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$C1_PY $X "$@" > "$b.configure.log" 2>&1 || { echo "configure rc=$?"; exit 3; }
if [ "$targets" = all ]; then T=""; else T="--target $targets"; fi
taskset -c $C1_CPUS cmake --build "$b" $T --parallel 2 > "$b.build.log" 2>&1; rc=$?
echo "build rc=$rc"
[ $rc -eq 0 ] && { sha256sum "$b/motioncorr" | tee -a "$b.binaries.sha256"; grep -h -- '-O3' "$b/CMakeFiles/motioncorr.dir/flags.make" | head -1; }
exit $rc
