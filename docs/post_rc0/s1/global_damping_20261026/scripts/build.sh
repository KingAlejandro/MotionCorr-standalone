#!/bin/bash
# usage: build.sh base|cand   Release build of the staged tree $DS_SC/src-<arm> into $DS_SC/build-<arm>; -j8 inside CPUs 48-55.
# pbzip2 is absent on cpu64, so MC_REQUIRE_ALL_DECODERS stays at its default OFF; the repo then waives the pbzip2 compressed-MRC cases (UNRUN).
# base builds only the motioncorr binary; cand builds everything (the full CPU CTest needs the test executables).
set -u
source "$(dirname "$0")/env.sh" || exit 1
arm=$1; src=$DS_SC/src-$arm; b=$DS_SC/build-$arm
if [ "$arm" = base ]; then T="--target motioncorr"; else T=""; fi
lane cmake -S "$src" -B "$b" -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$DS_PY -DCUDA=OFF > "$b.configure.log" 2>&1; rc=$?
echo "configure rc=$rc"; [ $rc -eq 0 ] || exit 3
lane cmake --build "$b" $T --parallel 8 > "$b.build.log" 2>&1; rc=$?
echo "build rc=$rc"
[ $rc -eq 0 ] || exit 4
sha256sum "$b/motioncorr" | tee "$b.binaries.sha256"
grep -h -- '-O3' "$b/CMakeFiles/motioncorr.dir/flags.make" | head -1 | tee "$b.flags.txt"
grep -E "CMAKE_BUILD_TYPE" "$b/CMakeCache.txt"
