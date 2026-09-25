#!/bin/bash
# Build MotionCorr-standalone PR #51 head (306bc67) with CUDA, Release.
# Must be invoked under taskset -c 96-103 and while holding /tmp/motioncorr-bench.lock.
set -euo pipefail

SRC=/home/alex/mc3-compare/MotionCorr-306bc67
BUILD="$SRC/build-mc3cmp"
SHA=306bc67ecaa142d247ac9cee53b05ae0a3fc116c

echo "== affinity: $(taskset -cp $$ 2>&1)"
echo "== nproc:    $(nproc)"

cd "$SRC"
git checkout --quiet "$SHA"
echo "== source sha: $(git rev-parse HEAD)"
echo "== tree clean: $(git status --porcelain | wc -l) modified files"

rm -rf "$BUILD"
cmake -S "$SRC" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES=80 \
  -DBUILD_TESTING=OFF >/dev/null

# the -O0 trap: never quote a timing without reading this back
echo "== CXX flags:  $(grep -m1 CXX_FLAGS  "$BUILD/CMakeFiles/motioncorr_core.dir/flags.make")"
echo "== CUDA flags: $(grep -m1 CUDA_FLAGS "$BUILD/CMakeFiles/motioncorr_core.dir/flags.make" || echo '(none)')"

time cmake --build "$BUILD" --parallel 8 2>&1 | tail -15

echo "== result"
ls -l "$BUILD/motioncorr"
sha256sum "$BUILD/motioncorr"
