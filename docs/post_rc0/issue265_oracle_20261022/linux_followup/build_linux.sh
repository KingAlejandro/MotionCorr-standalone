#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Linux CPU-only provenance preflight and harness build for the #265 oracle follow-up.
# Reads the exact-main base source and CPU library READ ONLY, builds only the original
# harness against that library, runs NO fixture. Pinned to CPU 16, nonblocking locks.
# usage: taskset -c 16 build_linux.sh <scratch-dir> <main-blob-manifest> <harness.cpp>
set -u
W=$1; MANIFEST=$2; HARNESS=$3
G=/mnt/clathrin/alex-motioncorr-guard264-20261022-0a1f64ab3e19
SRC=$G/src-base; BLD=$G/build-base-cpu
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 LC_ALL=C GIT_OPTIONAL_LOCKS=0
P=$W/preflight; mkdir -p "$P" "$W/bin"
exec 9>/tmp/motioncorr-star265-cpu16.lock
flock -n 9 || { echo "CPU16 LOCK CONTENTION: stop"; exit 91; }
exec 8>/tmp/motioncorr-build.lock
flock -n 8 || { echo "BUILD LOCK CONTENTION: stop"; exit 92; }
{ date -u +%FT%TZ; hostname; uptime; echo "affinity: $(taskset -cp $$)"; grep Cpus_allowed_list /proc/self/status
  echo "--- processes whose last CPU is 16:"; ps -eo user:12,pid,psr,pcpu,args | awk '$3==16' | cut -c1-160
  df -h /mnt/clathrin | tail -1; } > "$P/host_before_build.txt" 2>&1
# --- source identity (read only; no git index writes) ---
{ echo "src HEAD: $(git -C "$SRC" rev-parse HEAD)"
  echo "porcelain --ignored lines: $(git -C "$SRC" status --porcelain --ignored | wc -l)"
  git -C "$SRC" ls-files -z | while IFS= read -r -d "" f; do printf '%s  %s\n' "$(git -C "$SRC" hash-object -- "$SRC/$f")" "$f"; done | LC_ALL=C sort -k2 > "$P/src_blobs.txt"
  echo "tracked files hashed: $(wc -l < "$P/src_blobs.txt")"
  LC_ALL=C sort -k2 "$MANIFEST" > "$P/main_blobs.sorted.txt"
  if cmp -s "$P/main_blobs.sorted.txt" "$P/src_blobs.txt"; then echo "BLOBS IDENTICAL to main manifest"; else echo "BLOBS DIFFER from main manifest"; fi
  sha256sum "$P/src_blobs.txt" "$P/main_blobs.sorted.txt"
  grep -E ' src/(micrograph_model\.(cpp|h)|metadata_table\.(cpp|h)|metadata_label\.h|error\.h)$' "$P/src_blobs.txt"
  echo "files newer than the library:"; find "$SRC" -path "$SRC/.git" -prune -o -type f -newer "$BLD/libmotioncorr_core.a" -print | head -5
} > "$P/source_identity.txt" 2>&1
# --- library / configuration identity ---
{ grep -E '^(CMAKE_BUILD_TYPE|CUDA|USE_NVCOMP|CMAKE_HOME_DIRECTORY|CMAKE_CXX_COMPILER|CMAKE_CXX_FLAGS|CMAKE_CXX_FLAGS_RELEASE|MOTIONCORR_CPU_DOSE_SYMMETRY|TIMING):' "$BLD/CMakeCache.txt"
  echo "--- flags.make"; grep -v '^#' "$BLD/CMakeFiles/motioncorr_core.dir/flags.make"
  echo "--- link.txt"; cat "$BLD/CMakeFiles/motioncorr.dir/link.txt"
  ls -l --time-style=full-iso "$BLD/libmotioncorr_core.a"; sha256sum "$BLD/libmotioncorr_core.a"
  echo "cuda/cufft/nvcomp symbols in library: $(nm -C "$BLD/libmotioncorr_core.a" 2>/dev/null | grep -i -c -E 'cuda|cufft|nvcomp')"
  echo "cuda libs in base motioncorr ldd: $(ldd "$BLD/motioncorr" | grep -i -c -E 'cuda|cufft|nvcomp')"
  echo "--- compiler"; /usr/bin/c++ --version | head -1; ld --version | head -1; ldd --version | head -1
  dpkg -l libstdc++6 libc6 2>/dev/null | tail -2
} > "$P/library_identity.txt" 2>&1
grep -q "BLOBS IDENTICAL" "$P/source_identity.txt" || { echo "source identity mismatch: UNRUN"; exit 93; }
grep -q "^CUDA:BOOL=OFF" "$P/library_identity.txt" || { echo "library not CUDA=OFF: UNRUN"; exit 94; }
# --- build the original harness against the verified library, flags from its own build ---
FLAGS=$BLD/CMakeFiles/motioncorr_core.dir/flags.make
DEFS=$(sed -n 's/^CXX_DEFINES = //p' "$FLAGS"); INCS=$(sed -n 's/^CXX_INCLUDES = //p' "$FLAGS"); CXXF=$(sed -n 's/^CXX_FLAGS = //p' "$FLAGS")
LIBS=$(sed 's/.* -o motioncorr  *libmotioncorr_core\.a//' "$BLD/CMakeFiles/motioncorr.dir/link.txt")
{ echo "CXX=/usr/bin/c++"; echo "DEFS=$DEFS"; echo "INCS=$INCS"; echo "CXXFLAGS=$CXXF"; echo "LIBS=$LIBS"; } > "$P/build_options.txt"
# shellcheck disable=SC2086
/usr/bin/c++ $CXXF $DEFS $INCS "$HARNESS" "$BLD/libmotioncorr_core.a" $LIBS -o "$W/bin/roundtrip_oracle_linux" > "$P/harness_build.stdout" 2> "$P/harness_build.stderr"
echo $? > "$P/harness_build.exit"
{ sha256sum "$W/bin/roundtrip_oracle_linux" "$BLD/libmotioncorr_core.a" "$HARNESS"
  echo "--- ldd"; ldd "$W/bin/roundtrip_oracle_linux"
  echo "cuda libs in harness ldd: $(ldd "$W/bin/roundtrip_oracle_linux" | grep -i -c -E 'cuda|cufft|nvcomp')"
  echo "--- readelf NEEDED"; readelf -d "$W/bin/roundtrip_oracle_linux" | grep NEEDED
} > "$P/harness_identity.txt" 2>&1
{ date -u +%FT%TZ; ps -eo user:12,pid,psr,pcpu,args | awk '$3==16' | cut -c1-160; } > "$P/host_after_build.txt" 2>&1
cat "$P/harness_build.exit"
