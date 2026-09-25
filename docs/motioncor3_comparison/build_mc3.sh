#!/bin/bash
# Build upstream MotionCor3 on 4GPUs.
#   $1 = variant: "stock" (upstream makefile11 flags) or "o3" (host -O3)
# Must be invoked under taskset -c 96-103 and while holding /tmp/motioncorr-bench.lock.
#
# Deviation from the upstream recipe, and why:
#   `make exe -f makefile11` links the PREBUILT archives LibSrc/Lib/{libmrcfile,libutil}.a
#   that upstream commits to the repository. Those objects are non-PIE, and Ubuntu 24.04's
#   gcc defaults to PIE, so the link fails with
#     relocation R_X86_64_32 against `__gxx_personality_v0' can not be used when making a PIE object
#   Rather than paper over it with -no-pie (which would keep opaque prebuilt binaries in the
#   measured executable), both archives are rebuilt from the sources shipped in the same
#   upstream repo, using that repo's own LibSrc makefiles and the same host flags as the
#   variant being built.
set -euo pipefail

VARIANT="${1:?variant: stock|o3}"
ROOT=/home/alex/mc3-compare
SRC="$ROOT/MotionCor3-$VARIANT"
PREFIX="$ROOT/prefix"
CUDAHOME=/usr/local/cuda-12.8

case "$VARIANT" in
  stock) HOSTFLAGS="-c -g -pthread -m64" ;;     # upstream verbatim: no -O
  o3)    HOSTFLAGS="-c -O3 -pthread -m64" ;;    # only change: host optimisation
  *) echo "unknown variant"; exit 2 ;;
esac

echo "== affinity: $(taskset -cp $$ 2>&1 | sed 's/.*: //')   nproc: $(nproc)"
rm -rf "$SRC"
git clone --quiet "$ROOT/MotionCor3" "$SRC"
cd "$SRC"
git checkout --quiet dd8b6831ae66ef016fb7ef3b9b6172f8b56c79aa
echo "== source sha: $(git rev-parse HEAD)   dirty files: $(git status --porcelain | wc -l)"
echo "== host flags: $HOSTFLAGS"

echo "== rebuilding vendored LibSrc archives from source"
sha256sum LibSrc/Lib/libmrcfile.a LibSrc/Lib/libutil.a | sed 's/^/   shipped: /'
make -C LibSrc/Util    -j 8 all CFLAG="$HOSTFLAGS"  >/dev/null
make -C LibSrc/Mrcfile -j 8 all CFLAGS="$HOSTFLAGS -IInclude -I$SRC/LibSrc/Include" >/dev/null
sha256sum LibSrc/Lib/libmrcfile.a LibSrc/Lib/libutil.a | sed 's/^/   rebuilt: /'

echo "== building MotionCor3"
time make exe -f makefile11 -j 8 \
  CUDAHOME="$CUDAHOME" CONDA="$PREFIX" CFLAG="$HOSTFLAGS" 2>&1 | tail -12

echo "== result"
ls -l MotionCor3
sha256sum MotionCor3
