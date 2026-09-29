#!/usr/bin/env bash
set -euo pipefail
set -x
ROOT=${1:?validation root}
SRC="$ROOT/src"
PY="$HOME/.mc-venv/bin/python3"
export PATH="$HOME/.mc-venv/bin:$PATH"
date -Is
hostname
git -C "$SRC" rev-parse HEAD
git -C "$SRC" status --porcelain
test -z "$(git -C "$SRC" status --porcelain)"
# The reviewed delta changes Python only; the built native CPU code is identical.
test -z "$(git -C "$SRC" diff 881daa1..HEAD -- src CMakeLists.txt)"
sha256sum "$ROOT/build/motioncorr"
ps -p $$ -o pid,ppid,lstart,args
grep Cpus_allowed_list /proc/$$/status
numactl --show
"$PY" "$SRC/tests/test_multi_gpu_scheduling.py" --binary "$ROOT/build/motioncorr"
"$PY" "$SRC/docs/multi_gpu/negative_controls.py" --json-out "$ROOT/review_delta_mutations.json"
"$PY" "$SRC/tools/validate_test_collection.py" --test-dir "$ROOT/build" --dump-json "$ROOT/review_delta_collection.json"
ctest --test-dir "$ROOT/build" --output-on-failure -j 1
"$PY" "$SRC/docs/multi_gpu/port_validation/e2e_cpu_arm.py" --binary "$ROOT/build/motioncorr" --src "$SRC" --work "$ROOT/e2e_review_delta" --json-out "$ROOT/e2e_review_delta.json"
date -Is
echo REVIEW_DELTA_PASS
