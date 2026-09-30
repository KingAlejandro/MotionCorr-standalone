#!/usr/bin/env bash
set -euo pipefail
set -x
ROOT=/home/ubuntu/mc-pr117-review-p1-20260929
SRC=/home/ubuntu/mc-pr117-final-20260929T1316/src
BUILD=/home/ubuntu/mc-pr117-final-20260929T1316/build
PY=/home/ubuntu/.mc-venv/bin/python3
export PATH=/home/ubuntu/.mc-venv/bin:$PATH
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
source_revision=${1:?source commit}
date -Is
hostname
ps -p $$ -o pid,ppid,lstart,args
readlink /proc/$$/exe
grep Cpus_allowed_list /proc/$$/status
numactl --show
cat /proc/loadavg
ps -p 1156942,1635429 -o pid,lstart,comm
test -z "$(git -C "$SRC" status --porcelain)"
git -C "$SRC" fetch "$ROOT/fix.bundle" HEAD
test "$(git -C "$SRC" rev-parse FETCH_HEAD)" = "$source_revision"
git -C "$SRC" checkout --detach "$source_revision"
test -z "$(git -C "$SRC" status --porcelain)"
git -C "$SRC" rev-parse HEAD
# Only Python/tests/evidence changed. Reuse the retained binary with identical C++.
test -z "$(git -C "$SRC" diff 75a6296..HEAD -- src CMakeLists.txt)"
sha256sum "$BUILD/motioncorr"
"$PY" "$SRC/tests/test_multi_gpu_scheduling.py" --binary "$BUILD/motioncorr"
"$PY" "$SRC/docs/multi_gpu/negative_controls.py" --json-out "$ROOT/mutations.json"
"$PY" "$SRC/tools/validate_test_collection.py" --test-dir "$BUILD" --dump-json "$ROOT/collection.json"
ctest --test-dir "$BUILD" --output-on-failure -j 1
"$PY" "$SRC/docs/multi_gpu/port_validation/e2e_cpu_arm.py" --binary "$BUILD/motioncorr" --src "$SRC" --work "$ROOT/e2e" --json-out "$ROOT/e2e.json"
date -Is
cat /proc/loadavg
ps -p 1156942,1635429 -o pid,lstart,comm
echo REVIEW_P1_VALIDATION_PASS
