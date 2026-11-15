#!/bin/bash
# usage: build_h5.sh   Two Release builds of $DS_SC/src-h5 (CUDA=OFF, -j8 inside CPUs 48-55): build-h5off (default) and build-h5on (-DMC_EXPERIMENT_CCF_DC=ON).
set -u
source "$(dirname "$(readlink -f "$0")")/env.sh" || exit 1
src=$DS_SC/src-h5
for v in off on; do
  b=$DS_SC/build-h5$v; X=""; [ $v = on ] && X="-DMC_EXPERIMENT_CCF_DC=ON"
  lane cmake -S "$src" -B "$b" -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$DS_PY -DCUDA=OFF $X > "$b.configure.log" 2>&1; echo "h5$v configure rc=$?"
  lane cmake --build "$b" --parallel 8 > "$b.build.log" 2>&1; rc=$?; echo "h5$v build rc=$rc"; [ $rc -eq 0 ] || exit 4
  sha256sum "$b/motioncorr" | tee "$b.binaries.sha256"
  grep -h -- '-O3' "$b/CMakeFiles/motioncorr.dir/flags.make" | head -1 | tee "$b.flags.txt"
done
