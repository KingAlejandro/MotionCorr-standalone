#!/usr/bin/env bash
# Driver for the Issue #85 lane A TIFF ingest attribution benchmark.
#
# Records the identity every retained arm needs -- host, kernel, CPU mask,
# GPU UUID, source revision, binary hash, input hashes, libtiff version --
# then runs the decode attribution under separate storage regimes and the
# comparator controls. Regimes are never merged into one table.
#
# Usage:
#   run_tiff_ingest_bench.sh --build-dir DIR --movies-dir DIR --out DIR \
#       [--mask 96-119] [--workers 1,2,4,8,16,24] [--repeats 3] \
#       [--phases selftest,warm,cold,tmpfs,h2d]

set -euo pipefail

BUILD_DIR=""
MOVIES_DIR=""
OUT=""
MASK="96-119"
WORKERS="1,2,4,8,16,24"
REPEATS=3
PHASES="selftest,warmrep,warmall,cold,tmpfs,h2d"
GPU_ORDINAL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-dir)  BUILD_DIR="$2"; shift 2;;
    --movies-dir) MOVIES_DIR="$2"; shift 2;;
    --out)        OUT="$2"; shift 2;;
    --mask)       MASK="$2"; shift 2;;
    --workers)    WORKERS="$2"; shift 2;;
    --repeats)    REPEATS="$2"; shift 2;;
    --phases)     PHASES="$2"; shift 2;;
    --gpu)        GPU_ORDINAL="$2"; shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done
[[ -n "$BUILD_DIR" && -n "$MOVIES_DIR" && -n "$OUT" ]] || {
  echo "need --build-dir, --movies-dir and --out" >&2; exit 2; }

mkdir -p "$OUT/raw"
BENCH="$BUILD_DIR/tiff_ingest_bench"
H2D="$BUILD_DIR/h2d_stage_bench"
[[ -x "$BENCH" ]] || { echo "missing $BENCH" >&2; exit 1; }

has_phase() { [[ ",$PHASES," == *",$1,"* ]]; }

# Per-core jiffy snapshot restricted to the cores in $MASK.
cpu_stat_snapshot() {
  local first last
  first=${MASK%%-*}; last=${MASK##*-}
  for ((c=first; c<=last; c++)); do
    grep -E "^cpu${c} " /proc/stat || true
  done
}

# Representative movie plus the whole set. Per #85 the single default movie is
# not representative, so no load-bearing number comes from it alone.
mapfile -t ALL_MOVIES < <(ls "$MOVIES_DIR"/*.tiff | sort)
REP_MOVIE="$MOVIES_DIR/20170629_00021_frameImage.tiff"
[[ -f "$REP_MOVIE" ]] || REP_MOVIE="${ALL_MOVIES[0]}"

movie_args() { for m in "$@"; do printf -- "--movie %s " "$m"; done; }

# ------------------------------------------------------------------ identity
ID="$OUT/identity.txt"
{
  echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host=$(hostname)"
  echo "kernel=$(uname -srvmo)"
  echo "requested_mask=$MASK"
  echo "nproc_total=$(nproc --all)"
  echo "cpu_model=$(lscpu | sed -n 's/^Model name: *//p')"
  echo "numa=$(lscpu | sed -n 's/^NUMA node(s): *//p')"
  for n in $(lscpu | sed -n 's/^NUMA node\([0-9]*\) CPU(s): *\(.*\)/\1:\2/p'); do
    echo "numa_node_cpus=$n"
  done
  echo "mem_total_kb=$(sed -n 's/^MemTotal: *//p' /proc/meminfo)"
  echo "governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)"
  echo "libtiff=$(dpkg -s libtiff-dev 2>/dev/null | sed -n 's/^Version: //p' || echo unknown)"
  echo "zlib=$(dpkg -s zlib1g 2>/dev/null | sed -n 's/^Version: //p' || echo unknown)"
  echo "gcc=$(g++ --version | head -1)"
  echo "loadavg_at_start=$(cat /proc/loadavg)"
  echo "omp_proc_bind=${OMP_PROC_BIND:-<unset, matches production>}"
  echo "omp_num_threads=${OMP_NUM_THREADS:-<unset>}"
  # A git call that fails must not look like a clean tree. When the build
  # tree was transferred without .git, identify the compiled bytes directly.
  if git -C "${SRC_DIR:-$PWD}" rev-parse HEAD >/dev/null 2>&1; then
    echo "source_revision=$(git -C "${SRC_DIR:-$PWD}" rev-parse HEAD)"
    echo "source_dirty_files=$(git -C "${SRC_DIR:-$PWD}" status --porcelain | wc -l)"
  else
    echo "source_revision=UNAVAILABLE (no git metadata in ${SRC_DIR:-$PWD})"
    echo "source_dirty_files=UNAVAILABLE"
  fi
  echo "source_revision_declared=${LANE_BASE_REV:-not-declared}"
  echo "bench_sha256=$(sha256sum "$BENCH" | cut -d' ' -f1)"
  [[ -x "$H2D" ]] && echo "h2d_sha256=$(sha256sum "$H2D" | cut -d' ' -f1)"
  echo "storage_mount=$(df -hT "$MOVIES_DIR" | tail -1)"
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=index,uuid,name,driver_version --format=csv,noheader \
      | sed 's/^/gpu=/'
    nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader \
      | sed 's/^/gpu_compute_apps_at_start=/'
  fi
} > "$ID"

cpu_stat_snapshot > "$OUT/cpu_stat_before.txt"

# Content manifest of everything compiled. This is the authoritative source
# identity; it does not depend on git metadata surviving the transfer.
( cd "${SRC_DIR:-$PWD}" && find src benchmarks CMakeLists.txt -type f \
    \( -name '*.cpp' -o -name '*.h' -o -name '*.cu' -o -name '*.cuh' \
       -o -name '*.c' -o -name '*.cc' -o -name '*.in' -o -name 'CMakeLists.txt' \) \
    | LC_ALL=C sort | xargs sha256sum ) > "$OUT/source_manifest_sha256.txt"
{
  echo "source_manifest_files=$(wc -l < "$OUT/source_manifest_sha256.txt")"
  echo "source_manifest_sha256=$(sha256sum "$OUT/source_manifest_sha256.txt" | cut -d' ' -f1)"
} >> "$ID"

echo "== input hashes (this takes a minute) =="
sha256sum "${ALL_MOVIES[@]}" > "$OUT/input_sha256.txt"

# ------------------------------------------------------- comparator controls
#
# Runs before any timing. First establishes which mutation classes each
# comparator can see, then injects a real fault into a live arm's output so a
# PASS elsewhere in this run is falsifiable.
if has_phase selftest; then
  echo "== selftest: comparator sensitivity =="
  taskset -c "$MASK" "$BENCH" --selftest --repeats 1 --workers 8 \
    --arm production_image_read --movie "$REP_MOVIE" \
    --tag selftest --out "$OUT/raw/selftest.json" 2> "$OUT/raw/selftest.log"

  for M in value_1ulp swap_pixels_in_row swap_rows_in_frame yflip_one_frame swap_two_frames; do
    echo "== injection control: $M into a live production_image_read =="
    taskset -c "$MASK" "$BENCH" --repeats 1 --workers 8 \
      --arm production_image_read --movie "$REP_MOVIE" \
      --inject "$M" --inject-arm production_image_read \
      --tag "inject_$M" --out "$OUT/raw/inject_$M.json" \
      2> "$OUT/raw/inject_$M.log"
  done

  echo "== uninjected control: the same arm must pass =="
  taskset -c "$MASK" "$BENCH" --repeats 1 --workers 8 \
    --arm production_image_read --movie "$REP_MOVIE" \
    --tag inject_none --out "$OUT/raw/inject_none.json" \
    2> "$OUT/raw/inject_none.log"
fi

# ------------------------------------------------- regime 1: warm page cache
if has_phase warmrep; then
  echo "== warm ext4, representative movie, full worker sweep =="
  taskset -c "$MASK" "$BENCH" --regime warm --repeats "$REPEATS" --workers "$WORKERS" \
    --movie "$REP_MOVIE" --tag warm_ext4_rep \
    --out "$OUT/raw/warm_ext4_rep.json" 2> "$OUT/raw/warm_ext4_rep.log"
fi

if has_phase warmall; then
  # The full 19-arm x 6-worker sweep costs ~22 min per movie, so running it on
  # all 24 would take about nine hours. The worker-scaling question is answered
  # by the representative-movie sweep above; what the whole set has to answer is
  # whether the per-movie attribution generalises beyond one movie, which #85
  # explicitly requires because movie 00021 is known to run low. So the set runs
  # the attribution chain only, at the production worker count and at the
  # per-mask maximum. Arms omitted from this phase are named here rather than
  # silently dropped.
  # One invocation, every arm, so the arms are interleaved inside a single
  # process and the chain differences mean something. Running one invocation
  # per arm would make each arm re-pay this phase's per-movie fixed cost (a
  # serial reference decode plus the oracle pass) and, worse, would measure
  # each arm under different machine conditions.
  echo "== warm ext4, all 24 movies, all arms at W=8 and W=24 =="
  # shellcheck disable=SC2046
  taskset -c "$MASK" "$BENCH" --regime warm --repeats "$REPEATS" --workers 8,24 \
    $(movie_args "${ALL_MOVIES[@]}") --tag warm_ext4_all24 \
    --out "$OUT/raw/warm_ext4_all24.json" 2> "$OUT/raw/warm_ext4_all24.log"
fi

# ------------- regime 2: cold, per-file page-cache eviction, local ext4
# Only the storage-sensitive arms; posix_fadvise(DONTNEED) touches our file
# alone, so no other user's cached data is evicted.
if has_phase cold; then
  echo "== cold ext4 (per-file fadvise), storage-sensitive arms, all 24 movies =="
  for ARM in pread_whole_file pread_strip_extents tiff_read_raw_strip \
             tiff_decode_only persistent_handle_to_f32 production_image_read; do
    # shellcheck disable=SC2046
    taskset -c "$MASK" "$BENCH" --regime cold --repeats "$REPEATS" --workers 1,8,24 \
      --arm "$ARM" $(movie_args "${ALL_MOVIES[@]}") --tag "cold_ext4_$ARM" \
      --out "$OUT/raw/cold_ext4_$ARM.json" 2> "$OUT/raw/cold_ext4_$ARM.log"
  done
fi

# ------------------------------- regime 3: tmpfs, no block layer at all
if has_phase tmpfs; then
  SHM="/dev/shm/mc85_$$"
  mkdir -p "$SHM"
  # shellcheck disable=SC2064
  trap "rm -rf '$SHM'" EXIT
  echo "== staging the representative movie and a 4-movie subset on tmpfs =="
  SUBSET=("${ALL_MOVIES[@]:0:4}")
  cp "$REP_MOVIE" "${SUBSET[@]}" "$SHM/" 2>/dev/null || cp "$REP_MOVIE" "$SHM/"
  SHM_REP="$SHM/$(basename "$REP_MOVIE")"
  mapfile -t SHM_SUBSET < <(ls "$SHM"/*.tiff | sort)

  taskset -c "$MASK" "$BENCH" --regime warm --repeats "$REPEATS" --workers "$WORKERS" \
    --movie "$SHM_REP" --tag tmpfs_rep \
    --out "$OUT/raw/tmpfs_rep.json" 2> "$OUT/raw/tmpfs_rep.log"

  # Chain only on the tmpfs subset: the point of this regime is to remove the
  # block layer from the storage arms, not to repeat the worker sweep.
  for ARM in pread_strip_extents tiff_read_raw_strip tiff_decode_only \
             persistent_handle_to_f32 production_image_read; do
    # shellcheck disable=SC2046
    taskset -c "$MASK" "$BENCH" --regime warm --repeats "$REPEATS" --workers 8,24 \
      --arm "$ARM" $(movie_args "${SHM_SUBSET[@]}") --tag "tmpfs_subset_$ARM" \
      --out "$OUT/raw/tmpfs_subset_$ARM.json" 2> "$OUT/raw/tmpfs_subset_$ARM.log"
  done
fi

# ------------------------------------------------------------- H2D staging
if has_phase h2d && [[ -x "$H2D" ]]; then
  echo "== H2D staging, tutorial geometry =="
  nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory --format=csv,noheader \
    > "$OUT/raw/gpu_compute_apps_before.txt" 2>/dev/null || true
  taskset -c "$MASK" "$H2D" --nx 3710 --ny 3838 --frames 24 --repeats 7 \
    --device "$GPU_ORDINAL" --tag h2d_tutorial \
    --out "$OUT/raw/h2d_tutorial.json" 2> "$OUT/raw/h2d_tutorial.log"
  nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory --format=csv,noheader \
    > "$OUT/raw/gpu_compute_apps_after.txt" 2>/dev/null || true
fi

cpu_stat_snapshot > "$OUT/cpu_stat_after.txt"
python3 - "$OUT/cpu_stat_before.txt" "$OUT/cpu_stat_after.txt" > "$OUT/cpu_stat_delta.txt" <<'PYSTAT' || true
import sys
def load(p):
    d={}
    for line in open(p):
        f=line.split()
        if f and f[0].startswith("cpu"):
            d[f[0]]=[int(x) for x in f[1:]]
    return d
a,b=load(sys.argv[1]),load(sys.argv[2])
tot_busy=tot_all=0
print(f"{'cpu':>8} {'busy_jiffies':>13} {'total_jiffies':>14} {'busy_pct':>9}")
for k in sorted(a, key=lambda s:int(s[3:])):
    if k not in b: continue
    d=[y-x for x,y in zip(a[k],b[k])]
    total=sum(d); idle=d[3]+d[4]; busy=total-idle
    tot_busy+=busy; tot_all+=total
    print(f"{k:>8} {busy:>13} {total:>14} {100*busy/total if total else 0:>8.1f}%")
print(f"\nmask busy share over the whole run: "
      f"{100*tot_busy/tot_all if tot_all else 0:.1f}% "
      f"(our own work is included; a low number means little was left for anyone else "
      f"to have taken, a high one needs the per-arm CPU times to attribute)")
PYSTAT

# ------------------------------------------------ shared-host interference
# ps %CPU is a lifetime average and cannot see a burst inside our window, so
# witness with /proc/stat deltas on the cores we were actually pinned to.
{
  echo "loadavg_at_end=$(cat /proc/loadavg)"
  echo "interference_witness=see cpu_stat_delta.txt"
} >> "$ID"
echo "== done; raw JSON in $OUT/raw =="
