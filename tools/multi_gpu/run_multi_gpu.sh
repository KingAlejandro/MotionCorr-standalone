#!/bin/bash
# Smallest safe multi-GPU movie scheduling for MotionCorr --use_own.
#
# Process-level only: NO production source change. Each worker is the stock
# binary given a disjoint slice of the movies STAR and its own --gpu and --o.
#
# Why separate output directories rather than one shared --o:
#   Per-movie outputs (.mrc/.star/.eps/.log) are already unique, but every
#   process also writes fixed-path aggregates at the end of its run --
#   corrected_micrographs.star (via a .tmp + rename), logfile.pdf, header.pdf,
#   batch.pdf, all_batches.pdf (read-modify-write), <pdf>.lst scratch, and
#   corrected_micrographs_*.eps. Concurrent writers race on all of those.
#   Separate directories avoid every one of those races with no code change.
#
# Why whole-movie granularity:
#   executeOwnMotionCorrection calls init_random_generator(random_seed) per
#   movie (src/motioncorr_runner.cpp:1578), so a movie's result does not depend
#   on which process ran it or its position in the batch. Splitting *within* a
#   movie would not be safe; splitting *between* movies is.
#
# KNOWN LIMITATION (read before using in production):
#   This produces N per-worker corrected_micrographs.star and N logfile.pdf,
#   not one of each. --merge-star below reconstructs a single dataset STAR by
#   re-running the binary over the full STAR with --only_do_unfinished against
#   a merged tree, which works because the merge step re-reads every per-movie
#   .star from disk. The resulting logfile.pdf is NOT equivalent to a serial
#   run's: the PDF batch loop only globs movies in the *current* fn_micrographs,
#   which is empty on a resume-merge, so per-movie shift pages are omitted.
#   Producing a byte-faithful single PDF requires a source change and is out of
#   scope here.
set -euo pipefail

STAR=""; OUTROOT=""; GPUS=""; J=8; BIN=""; CPUS=""; MERGE=0
usage() { sed -n '2,30p' "$0"; exit 1; }
while [ $# -gt 0 ]; do case "$1" in
  --star) STAR=$2; shift 2;; --out) OUTROOT=$2; shift 2;;
  --gpus) GPUS=$2; shift 2;; --j) J=$2; shift 2;;
  --bin) BIN=$2; shift 2;; --cpus) CPUS=$2; shift 2;;
  --merge-star) MERGE=1; shift;; -h|--help) usage;;
  --) shift; break;; *) echo "unknown arg: $1" >&2; usage;; esac; done
[ -n "$STAR" ] && [ -n "$OUTROOT" ] && [ -n "$GPUS" ] && [ -n "$BIN" ] || usage
[ -e "$OUTROOT" ] && { echo "refusing to reuse existing --out: $OUTROOT" >&2; exit 2; }

IFS=',' read -r -a GPUARR <<< "$GPUS"
N=${#GPUARR[@]}
mkdir -p "$OUTROOT"
TASKSET=(); [ -n "$CPUS" ] && TASKSET=(taskset -c "$CPUS")

python3 "$(dirname "$0")/partition_star.py" --star "$STAR" --n "$N" --outdir "$OUTROOT" >/dev/null

pids=(); T0=$(date +%s.%N)
for ((k=0;k<N;k++)); do
  mkdir -p "$OUTROOT/w$k"
  "${TASKSET[@]}" "$BIN" --i "$OUTROOT/chunk_${N}way_${k}.star" --o "$OUTROOT/w$k/" \
      --gpu "${GPUARR[$k]}" --j "$J" "$@" > "$OUTROOT/w$k/run.log" 2>&1 &
  pids+=($!)
done
rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done
WALL=$(echo "$(date +%s.%N) - $T0" | bc)
echo "workers=$N gpus=$GPUS j=$J wall=${WALL}s rc=$rc"
[ "$rc" -ne 0 ] && { echo "FAIL: a worker exited non-zero; not merging" >&2; exit 3; }

if [ "$MERGE" -eq 1 ]; then
  M="$OUTROOT/merged"; mkdir -p "$M"
  for ((k=0;k<N;k++)); do
    (cd "$OUTROOT/w$k" && find . -type f \
        ! -name 'corrected_micrographs*.star' ! -name '*.pdf' ! -name '*.lst' \
        ! -name 'corrected_micrographs_*' ! -name 'run.log' \
        -exec cp -n --parents {} "$M"/ \;)
  done
  "${TASKSET[@]}" "$BIN" --i "$STAR" --o "$M/" --only_do_unfinished "$@" \
      > "$OUTROOT/merge.log" 2>&1 \
    && echo "merged dataset STAR: $M/corrected_micrographs.star (logfile.pdf is degraded - see header)" \
    || { echo "FAIL: merge step exited non-zero, see $OUTROOT/merge.log" >&2; exit 4; }
fi
