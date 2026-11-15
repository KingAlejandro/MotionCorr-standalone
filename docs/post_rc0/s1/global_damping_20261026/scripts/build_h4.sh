#!/bin/bash
# usage: build_h4.sh   Two Release builds of the staged tree $DS_SC/src-h4 (CUDA=OFF, -j8 inside CPUs 48-55):
#   build-h4off  default options (the #262 hook compiles to nothing)
#   build-h4on   -DMC_EXPERIMENT_CCF_DC=ON (hook built in; needs MC_EXPERIMENT_CCF_DC_ARM at run time)
# pbzip2 is absent on cpu64: MC_REQUIRE_ALL_DECODERS stays OFF (repo waiver).
set -u
source "$(dirname "$(readlink -f "$0")")/env.sh" || exit 1
src=$DS_SC/src-h4
for v in off on; do
  b=$DS_SC/build-h4$v; X=""; [ $v = on ] && X="-DMC_EXPERIMENT_CCF_DC=ON"
  lane cmake -S "$src" -B "$b" -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$DS_PY -DCUDA=OFF $X > "$b.configure.log" 2>&1; echo "h4$v configure rc=$?"
  lane cmake --build "$b" --parallel 8 > "$b.build.log" 2>&1; rc=$?; echo "h4$v build rc=$rc"; [ $rc -eq 0 ] || exit 4
  sha256sum "$b/motioncorr" | tee "$b.binaries.sha256"
  grep -h -- '-O3' "$b/CMakeFiles/motioncorr.dir/flags.make" | head -1 | tee "$b.flags.txt"
  grep -E "CMAKE_BUILD_TYPE|MC_EXPERIMENT_CCF_DC" "$b/CMakeCache.txt"
done
