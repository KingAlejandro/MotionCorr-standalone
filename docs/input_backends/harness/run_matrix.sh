#!/bin/bash
# run_matrix.sh <binary> <variant-dir> <outdir> <gpu-index> [extra motioncorr args...]
#
# Products land under <outdir> and nothing else does: the run's stdout, its
# resource record and the route witness go to siblings of <outdir>, because a
# harness file inside the tree is compared as if it were a product and makes
# every cross-arm comparison fail for a reason that is not a product difference.
set -u
BIN=$1; VAR=$2; OUT=$3; GPU=$4; shift 4
cd "$VAR" || exit 1
rm -rf "$OUT"; mkdir -p "$OUT"
/usr/bin/time -v "$BIN" --i movies.star --o "$OUT/" \
  --use_own --dose_weighting --dose_per_frame 1.277 \
  --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 \
  --j 8 --gpu "$GPU" --ingest_witness "$OUT.witness" "$@" \
  > "$OUT.stdout" 2> "$OUT.time"
rc=$?
echo "RC=$rc"
grep -E "Elapsed \(wall|Maximum resident|User time|System time" "$OUT.time"
echo "PRODUCTS=$(find "$OUT" -name '*.mrc' | wc -l)"
echo "ROUTES=$(sort "$OUT.witness" 2>/dev/null | awk '{print $2}' | sort | uniq -c | tr '\n' ' ')"
