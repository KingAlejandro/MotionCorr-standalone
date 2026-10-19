#!/bin/bash
# Negative control for item13_mrc.sh: the driver's exit status must be the grader's.
# Copies $QF_W/item13-mrc's JSON results into a throwaway workspace, then runs the driver in grade-only
# mode twice: unmodified (must exit 0) and with one record's verdict flipped (cuda-errors record 0,
# pass -> false; must exit nonzero). Exit 0 only if both hold.
set -u
: "${QF_W:?}" "${QF_CPUS:?}" "${QF_GPU_UUID:?}" "${QF_GPU_LOCK:?}"
T=$(cd "$(dirname "$0")" && pwd)
X=$(mktemp -d)
trap 'rm -rf "$X"' EXIT
mkdir -p $X/item13-mrc && cp $QF_W/item13-mrc/*.json $X/item13-mrc/ && rm -f $X/item13-mrc/grade.json
QF_W=$X QF_ITEM13_GRADE_ONLY=1 bash $T/item13_mrc.sh > $X/clean.out 2>&1; clean=$?
/home/alex/.mc-venv/bin/python3 - $X/item13-mrc/cuda-errors.json <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d['errors'][0]['pass'] = False; json.dump(d, open(p, 'w'))
PY
QF_W=$X QF_ITEM13_GRADE_ONLY=1 bash $T/item13_mrc.sh > $X/flipped.out 2>&1; flipped=$?
echo "unmodified: driver rc=$clean (want 0); one verdict flipped: driver rc=$flipped (want nonzero)"
grep -m1 'expected PASS, current FAIL' $X/flipped.out
[ $clean -eq 0 ] && [ $flipped -ne 0 ] && { echo "PROBE PASS"; exit 0; }
echo "PROBE FAIL"; exit 1
