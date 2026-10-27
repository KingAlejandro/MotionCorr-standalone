#!/bin/bash
# Stage C amendment-1 venue window (frozen before launch): the standalone guard once, read-only, and the Linux fake-child /
# guard-shim tests. No MotionCorr child, no GPU producer, no Stage C row, no retry. Run on 4GPUs as
#   setsid taskset -c 80-87 bash docs/post_rc0/ccf_dc_native_compat_20261026/evidence/stageC/amend1_window.sh <root> > <root>/logs/chain.out 2>&1 < /dev/null &
# where <root> is the staged subset holding tools/, test-data/ and docs/.
set -u
S=$(cd "${1:-.}" && pwd); L=$S/logs; mkdir -p "$L"      # root of the staged subset (holds tools/, test-data/, docs/)
PY=/home/alex/.mc-venv/bin/python3
GPU2=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598; FOREIGN=3983855
ts() { date -u +%FT%TZ; }
exec 10>>/tmp/motioncorr-dcnative-gpu2-cpu80-87.lock; flock -n 10 || { echo "STOP lease own busy $(ts)"; exit 90; }
exec 11>>/tmp/motioncorr-cuda-boundary-cpu80-87.lock; flock -n 11 || { echo "STOP lease cpu busy $(ts)"; exit 90; }
exec 12>>/tmp/motioncorr-gpu2-correctness.lock; flock -n 12 || { echo "STOP lease gpu2 busy $(ts)"; exit 90; }
echo "leases acquired (own, cpu80-87, gpu2-correctness) $(ts); affinity: $(taskset -cp $$)"
echo "python: $($PY -c 'import sys,numpy;print(sys.version.split()[0], numpy.__version__)')"
sha256sum "$S/tools/stageC_guard.sh" "$S/tools/ccf_dc_stagec_driver.py" "$S/tools/test_ccf_dc_stagec_guard.py" "$S/tools/test_ccf_dc_stagec_lifecycle.py" | tee "$L/hashes.txt"
echo "== 1. standalone guard, real entry (STAGEC_REAL=1), once, read-only $(ts)"
STAGEC_GPU2=$GPU2 STAGEC_FOREIGN_PID=$FOREIGN STAGEC_SCRATCH=$S STAGEC_REAL=1 PATH=/usr/local/cuda/bin:$PATH \
  bash "$S/tools/stageC_guard.sh" amend1-window 1 > "$L/guard.stdout" 2> "$L/guard.stderr"; echo "guard rc=$?" | tee "$L/guard.rc"
cat "$L/guard.stdout"; cat "$L/guard.stderr"
echo "== 2. guard shim tests on this Linux (awk/grep/df variants) $(ts)"
CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=2 $PY "$S/tools/test_ccf_dc_stagec_guard.py" -v > "$L/guard-tests.stdout" 2> "$L/guard-tests.stderr"; echo "guard-tests rc=$?" | tee "$L/guard-tests.rc"
tail -4 "$L/guard-tests.stderr"
echo "== 3. fake-child lifecycle and sampling tests, Linux /proc $(ts)"
CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=2 taskset -c 80,81 $PY "$S/tools/test_ccf_dc_stagec_lifecycle.py" -v > "$L/lifecycle.stdout" 2> "$L/lifecycle.stderr"; echo "lifecycle rc=$?" | tee "$L/lifecycle.rc"
tail -4 "$L/lifecycle.stderr"
echo "== scratch"; du -sh "$S" | tail -1
echo "== done $(ts)"
