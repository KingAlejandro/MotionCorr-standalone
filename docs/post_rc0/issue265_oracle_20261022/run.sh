#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Build the native harness against an existing motioncorr_core build and run it.
# usage: run.sh <source-tree> <cmake-build-dir-with-libmotioncorr_core.a> <outdir>
# The library build dir is produced beforehand with:
#   cmake -S <src> -B <build> -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=OFF
#   cmake --build <build> --target motioncorr_core -j1
# Compiler flags/defines/includes and the link line are taken from that build's own
# flags.make and motioncorr link.txt, so the harness matches the library exactly.
set -u
SRC=$1; BLD=$2; OUT=$3
HERE=$(cd "$(dirname "$0")" && pwd)
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
mkdir -p "$OUT/receipt"
R=$OUT/receipt
git -C "$SRC" rev-parse HEAD > "$R/source_head.txt"
git -C "$SRC" status --porcelain -- src CMakeLists.txt > "$R/source_dirty.txt"
FLAGS=$BLD/CMakeFiles/motioncorr_core.dir/flags.make
DEFS=$(sed -n 's/^CXX_DEFINES = //p' "$FLAGS")
INCS=$(sed -n 's/^CXX_INCLUDES = //p' "$FLAGS")
CXXF=$(sed -n 's/^CXX_FLAGS = //p' "$FLAGS")
# Link tail: everything after "-o motioncorr", minus the library path itself (re-added explicitly).
LIBS=$(sed 's/.* -o motioncorr  *libmotioncorr_core\.a//' "$BLD/CMakeFiles/motioncorr.dir/link.txt")
{
  echo "CXX=/usr/bin/c++"; /usr/bin/c++ --version
  echo "DEFS=$DEFS"; echo "INCS=$INCS"; echo "CXXFLAGS=$CXXF"; echo "LIBS=$LIBS"
} > "$R/build_options.txt" 2>&1
# shellcheck disable=SC2086
/usr/bin/c++ $CXXF $DEFS $INCS "$HERE/harness/roundtrip_oracle.cpp" "$BLD/libmotioncorr_core.a" $LIBS -o "$OUT/roundtrip_oracle" \
  > "$R/harness_build.stdout" 2> "$R/harness_build.stderr"
echo $? > "$R/harness_build.exit"
[ "$(cat "$R/harness_build.exit")" = 0 ] || exit 3
shasum -a 256 "$OUT/roundtrip_oracle" "$BLD/libmotioncorr_core.a" "$HERE/harness/roundtrip_oracle.cpp" "$HERE/fixtures.txt" > "$R/hashes.txt"
echo "argv: $OUT/roundtrip_oracle $HERE/fixtures.txt $OUT/run" > "$R/argv.txt"
"$OUT/roundtrip_oracle" "$HERE/fixtures.txt" "$OUT/run" > "$R/stdout.txt" 2> "$R/stderr.txt"
echo $? > "$R/exit.txt"
cat "$R/stdout.txt"; cat "$R/stderr.txt"
exit "$(cat "$R/exit.txt")"
