#!/bin/bash
#SBATCH -p scarf
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 03:00:00
#SBATCH -J mc85-laneA
#SBATCH -o /work4/cse/scarf1415/motioncorr/mc85-laneA/slurm-%j.out
#
# Issue #85 lane A on SCARF. This allocation exists for three things the
# shared 4-GPU VM cannot provide:
#
#   1. A shared/network filesystem. /work4 is PanFS. The VM mounts only local
#      ext4, so the "shared storage" regime the #85 benchmark contract asks
#      for was unmeasurable there.
#   2. Worker counts above the frame count. The movies have 24 frames, so
#      frame-level decode parallelism is capped at 24 and, at W=24, perfectly
#      balanced. Strip-batch decode can only be judged where frame-level
#      cannot go, which needs more than 24 cores.
#   3. An exclusive node. The VM runs other users' work, including another
#      #85 lane; every VM arm carries an interference witness because of it.
#
# LibTIFF here is 4.4 (libtiff.so.5); the VM has 4.5.1 (libtiff.so.6).
# Deflate timings are therefore NOT comparable across the two hosts and are
# never merged into one table.

set -uo pipefail

export OMP_NUM_THREADS=       # the harness sets num_threads per arm
unset OMP_NUM_THREADS
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OMP_PROC_BIND=         # unset: matches production, which sets neither
unset OMP_PROC_BIND
export TMPDIR=/tmp

D=/work4/cse/scarf1415/motioncorr/mc85-laneA
BUNDLE=/work4/cse/scarf1415/motioncorr/mc85-laneA.bundle
BUNDLE_SHA=a83351a09daeaea46ca2a028f2e7eaa2f6018d83739e399f02451cc137e8555b
PANFS_MOVIES=/work4/cse/scarf1415/motioncorr/mc-issue94/data/Movies
REP=20170629_00021_frameImage.tiff
WORKERS=1,2,4,8,16,24,32,48,64
REPEATS=3

E="$D/evidence"
mkdir -p "$E/raw"

echo "=== node ==="
hostname; nproc; lscpu | sed -n 's/^Model name: *//p'
free -g | head -2
echo "slurm_job_id=${SLURM_JOB_ID:-none}"
echo "slurm_nodelist=${SLURM_NODELIST:-none}"

# ---- source, from a bundle so the git revision travels with it -------------
echo "=== source ==="
got=$(sha256sum "$BUNDLE" | cut -d' ' -f1)
if [[ "$got" != "$BUNDLE_SHA" ]]; then
  echo "FATAL: bundle sha256 mismatch: got $got want $BUNDLE_SHA"; exit 1
fi
if [[ ! -d "$D/src" ]]; then
  git clone -q -b bench/issue85-tiff-ingest-attribution "$BUNDLE" "$D/src" || exit 1
fi
REV=$(git -C "$D/src" rev-parse HEAD)
echo "commit=$REV"
echo "dirty=[$(git -C "$D/src" status --porcelain | head -3)]"

# ---- build -----------------------------------------------------------------
if [[ ! -x "$D/build/tiff_ingest_bench" ]]; then
  cmake -S "$D/src" -B "$D/build" -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_TESTING=OFF -DBENCHMARKS=ON > "$D/cmake.log" 2>&1 || {
          echo "FATAL: configure failed"; tail -20 "$D/cmake.log"; exit 1; }
  cmake --build "$D/build" -j 32 --target tiff_ingest_bench > "$D/build.log" 2>&1 || {
          echo "FATAL: build failed"; tail -30 "$D/build.log"; exit 1; }
fi
BENCH="$D/build/tiff_ingest_bench"
grep -m1 CXX_FLAGS "$D/build/CMakeFiles/tiff_ingest_bench.dir/flags.make"
sha256sum "$BENCH"

# ---- identity --------------------------------------------------------------
{
  echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "venue=SCARF Slurm, exclusive node, partition scarf, constraint scarf23"
  echo "slurm_job_id=${SLURM_JOB_ID:-none}"
  echo "node=$(hostname)"
  echo "kernel=$(uname -srvmo)"
  echo "nproc=$(nproc)"
  echo "cpu_model=$(lscpu | sed -n 's/^Model name: *//p')"
  echo "numa=$(lscpu | sed -n 's/^NUMA node(s): *//p')"
  echo "mem_total_kb=$(sed -n 's/^MemTotal: *//p' /proc/meminfo)"
  echo "source_revision=$REV"
  echo "source_dirty_files=$(git -C "$D/src" status --porcelain | wc -l)"
  echo "bundle_sha256=$BUNDLE_SHA"
  echo "bench_sha256=$(sha256sum "$BENCH" | cut -d' ' -f1)"
  echo "cmake=$(cmake --version | head -1)"
  echo "gcc=$(gcc --version | head -1)"
  echo "libtiff_soname=$(ls /usr/lib64/libtiff.so.* | head -1)"
  echo "fftw=$(pkg-config --modversion fftw3 2>/dev/null)"
  echo "panfs_mount=$(df -PT "$PANFS_MOVIES" | tail -1)"
  echo "local_scratch=$(df -PT /tmp | tail -1)"
  echo "omp_proc_bind=${OMP_PROC_BIND:-<unset, matches production>}"
  echo "exclusive=yes (--exclusive), so no interference witness is needed"
} > "$E/identity.txt"
cat "$E/identity.txt"

( cd "$D/src" && find src benchmarks CMakeLists.txt -type f \
   \( -name '*.cpp' -o -name '*.h' -o -name '*.cu' -o -name '*.cuh' \
      -o -name '*.c' -o -name '*.cc' -o -name '*.in' -o -name 'CMakeLists.txt' \) \
   | LC_ALL=C sort | xargs sha256sum ) > "$E/source_manifest_sha256.txt"

echo "=== input hashes (PanFS) ==="
( cd "$PANFS_MOVIES" && sha256sum ./*.tiff ) > "$E/input_sha256_panfs.txt"
wc -l < "$E/input_sha256_panfs.txt"

mapfile -t PANFS_ALL < <(ls "$PANFS_MOVIES"/*.tiff | sort)
movie_args() { for m in "$@"; do printf -- "--movie %s " "$m"; done; }

# ---- controls, on this host's LibTIFF --------------------------------------
echo "=== controls ==="
"$BENCH" --selftest --repeats 1 --workers 8 --arm production_image_read \
  --movie "$PANFS_MOVIES/$REP" --tag scarf_selftest \
  --out "$E/raw/selftest.json" 2> "$E/raw/selftest.log"
for M in value_1ulp swap_pixels_in_row swap_rows_in_frame yflip_one_frame swap_two_frames; do
  "$BENCH" --repeats 1 --workers 8 --arm production_image_read \
    --movie "$PANFS_MOVIES/$REP" --inject "$M" --inject-arm production_image_read \
    --tag "scarf_inject_$M" --out "$E/raw/inject_$M.json" 2> "$E/raw/inject_$M.log"
done
"$BENCH" --repeats 1 --workers 8 --arm production_image_read \
  --movie "$PANFS_MOVIES/$REP" --tag scarf_inject_none \
  --out "$E/raw/inject_none.json" 2> "$E/raw/inject_none.log"

# ---- regime P1: PanFS, warm, representative movie, full worker sweep -------
echo "=== PanFS warm, representative movie, W=$WORKERS ==="
"$BENCH" --regime warm --repeats "$REPEATS" --workers "$WORKERS" \
  --movie "$PANFS_MOVIES/$REP" --tag scarf_panfs_warm_rep \
  --out "$E/raw/panfs_warm_rep.json" 2> "$E/raw/panfs_warm_rep.log"

# ---- regime L1: node-local /tmp, warm, same sweep --------------------------
LOCAL=/tmp/mc85_$SLURM_JOB_ID
mkdir -p "$LOCAL"
cp "$PANFS_MOVIES/$REP" "$LOCAL/"
echo "=== local /tmp warm, representative movie, W=$WORKERS ==="
"$BENCH" --regime warm --repeats "$REPEATS" --workers "$WORKERS" \
  --movie "$LOCAL/$REP" --tag scarf_local_warm_rep \
  --out "$E/raw/local_warm_rep.json" 2> "$E/raw/local_warm_rep.log"

# ---- regime P2: PanFS, warm, all 24, one interleaved invocation ------------
echo "=== PanFS warm, all 24 movies, W=8,24,64 ==="
# shellcheck disable=SC2046
"$BENCH" --regime warm --repeats "$REPEATS" --workers 8,24,64 \
  $(movie_args "${PANFS_ALL[@]}") --tag scarf_panfs_warm_all24 \
  --out "$E/raw/panfs_warm_all24.json" 2> "$E/raw/panfs_warm_all24.log"

# ---- regime P3: PanFS, cold file, all 24 -----------------------------------
# posix_fadvise(DONTNEED) on PanFS may or may not drop the client cache; the
# arm is reported as "cold-requested" and the measured numbers decide whether
# it actually went cold relative to P2.
echo "=== PanFS cold-requested, all 24 movies, W=8,24 ==="
# shellcheck disable=SC2046
"$BENCH" --regime cold --repeats "$REPEATS" --workers 8,24 \
  $(movie_args "${PANFS_ALL[@]}") --tag scarf_panfs_cold_all24 \
  --out "$E/raw/panfs_cold_all24.json" 2> "$E/raw/panfs_cold_all24.log"

rm -rf "$LOCAL"
echo "=== done ==="
ls -la "$E/raw"
