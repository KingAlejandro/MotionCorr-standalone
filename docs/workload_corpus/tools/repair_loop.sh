#!/bin/bash
# Re-run arms that have no usable record (tools/runfilter.py), up to MAXGEN passes.
# Usage: repair_loop.sh MAXGEN   (run from the corpus root on cpu64; paths below are relative to it)
MAXGEN=${1:-6}
for gen in $(seq 1 "$MAXGEN"); do
  n=$(python3 meta/suspects.py meta/families.json results "$gen" meta/redo.json | head -1 | cut -d' ' -f1)
  echo "pass $gen: $n arms without a usable record"
  [ "$n" = "0" ] && break
  python3 -I meta/run_matrix.py --families meta/families.json --corpus corpus \
      --binary bin/motioncorr-116eb04a-release --results results \
      --per-run-lock --settle-max 21600 --redo meta/redo.json
done
echo "repair loop done"
