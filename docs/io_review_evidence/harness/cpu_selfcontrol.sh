#!/bin/bash
# main-vs-main self-control at j1 on the CPU backend, plus a re-grade of the
# PR90 j1 A/B with the updated comparator. The self-control establishes what the
# auxiliary comparison does when the code is held constant and only the output
# directory name and wall-clock time change; without it, an auxiliary FAIL in
# the A/B cannot be attributed.
set -uo pipefail
source ~/.mc-venv/bin/activate
R=$HOME/mc-io-evidence
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
echo "=== provenance ==="; date -Is; hostname; uptime
md5sum $R/harness/compare_outputs.py
sha256sum $R/src-main/build-cpu/motioncorr $R/src-pr90/build-cpu/motioncorr

echo "=== regrade pr90 vs main, CPU j1, updated comparator (no rerun) ==="
taskset -c 56-63 python3 $R/harness/compare_outputs.py --repo $R/src-pr90 \
  --ref-binary $R/src-main/build-cpu/motioncorr --ref-label main \
  --test-binary $R/src-pr90/build-cpu/motioncorr --test-label pr90 \
  --tutorial $HOME/mc51/tutorial --threads 1 --skip-run \
  --work $R/ab-j1 --json $R/evidence/pr90_outputs_j1.json
echo "regrade exit=$?"

echo "=== self-control: main vs main, CPU j1, two independent runs ==="
rm -rf $R/ab-selfctl
taskset -c 56-63 python3 $R/harness/compare_outputs.py --repo $R/src-main \
  --ref-binary $R/src-main/build-cpu/motioncorr --ref-label mainA \
  --test-binary $R/src-main/build-cpu/motioncorr --test-label mainB \
  --tutorial $HOME/mc51/tutorial --threads 1 \
  --work $R/ab-selfctl --json $R/evidence/selfcontrol_main_vs_main_j1.json
echo "selfctl exit=$?"
echo "=== SELFCTL DONE ==="; date -Is
