#!/bin/bash
# build.sh <srcdir> <builddir> [cmake args...]
set -u
S="$1"; B="$2"; shift 2
NV=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
PY=/home/alex/mc-env/bin/python3
export PATH=/usr/local/cuda/bin:$PATH
L="$B.log"; rm -rf "$B"
cmake -S "$S" -B "$B" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
      -DPython3_EXECUTABLE="$PY" -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NV" "$@" > "$L" 2>&1
rc=$?; echo "CONFIGURE_RC=$rc" >> "$L"
[ $rc -ne 0 ] && { echo "FAIL-CONFIGURE $B (see $L)"; tail -20 "$L"; exit 1; }
cmake --build "$B" -j8 >> "$L" 2>&1
rc=$?; echo "BUILD_RC=$rc" >> "$L"
[ $rc -ne 0 ] && { echo "FAIL-BUILD $B (see $L)"; tail -30 "$L"; exit 1; }
echo "OK $B sha256=$(sha256sum "$B/motioncorr" | cut -d' ' -f1)"
