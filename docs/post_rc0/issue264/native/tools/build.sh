#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# usage: CFG=cpu|cuda|nvcomp build.sh SRCDIR BUILDDIR TARGET|all   Release, -j2, CPUs 14-15, nonblocking shared build lock (exit 5 on contention).
set -u
source "$(dirname "$0")/lane.sh" || exit 1
src=$1; b=$2; target=$3
[ -e "$b" ] && { echo "$b exists; refusing"; exit 4; }
exec 8>"$G_BUILD_LOCK"; flock -n 8 || { echo "build lock contended; stopping, no retry"; fuser $G_BUILD_LOCK; exit 5; }
CUDA_ARGS="-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8"
case "${CFG:-}" in cpu) X="-DCUDA=OFF";; cuda) X="$CUDA_ARGS -DUSE_NVCOMP=OFF";; nvcomp) X="$CUDA_ARGS -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$G_NVCOMP";; *) echo "CFG required"; exit 2;; esac
echo "source $(git -C $src rev-parse HEAD) dirty-diff-sha256 $(git -C $src diff | sha256sum | cut -c1-64) status-lines $(git -C $src status --porcelain | wc -l)"
taskset -c $G_CPUS cmake -S "$src" -B "$b" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=$G_PY -DMC_REQUIRE_ALL_DECODERS=ON $X > "$b.configure.log" 2>&1 || { echo "configure rc=$?"; exit 3; }
grep -q "CMAKE_HOME_DIRECTORY:INTERNAL=$src\$" "$b/CMakeCache.txt" || { echo "build tree not bound to $src"; exit 3; }
if [ "$target" = all ]; then T=""; else T="--target $target"; fi
taskset -c $G_CPUS cmake --build "$b" $T --parallel 2 > "$b.build.log" 2>&1; rc=$?
echo "build rc=$rc"
[ $rc -eq 0 ] && { sha256sum "$b/motioncorr" | tee "$b.binaries.sha256"; grep -h -- '-O3' "$b/CMakeFiles/motioncorr.dir/flags.make" | head -1; }
exit $rc
