#!/bin/bash
# RC0 candidate lane A: GPU0 GPU-eddb42fe-4f9a-adde-76d3-b924e14add54, CPUs 96-103, gpu0-correctness lock.
# Runs audited QF runbook items with the committed tools (unchanged). Correctness only, no timing claims.
# Order: item 2 (CTest CUDA) -> item 9 (#123 matrix, both CUDA executables) -> items 5/6 (campaign) -> item 11.
set -u
cd /mnt/clathrin/alex-motioncorr-rc0/W-RC0-CAND || exit 90
. ./env-laneA.sh
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
PY=/home/alex/.mc-venv/bin/python3
step() { echo "=== $1 start $(date -u +%FT%TZ)"; }
done_() { echo "=== $1 rc=$2 end $(date -u +%FT%TZ)"; }
step ctest-cuda; bash tools/run_ctest.sh cuda; done_ ctest-cuda "$(cat ctest-cuda.exit 2>/dev/null || echo none)"
for cfg in nvcomp cuda; do
  step matrix-$cfg
  QF_W=$QF_W flock $QF_GPU_LOCK taskset -c $QF_CPUS $PY tools/run_compact_ingest_support_matrix.py \
    --binary build-$cfg/motioncorr --device $QF_GPU_UUID --workdir matrix-$cfg --json matrix-$cfg.json > logs/matrix-$cfg.log 2>&1
  done_ matrix-$cfg $?
done
step campaign
QF_REF_CPU_BIN=/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-cpu/motioncorr \
  taskset -c $QF_CPUS $PY tools/product_campaign.py > logs/campaign.log 2>&1
rc=$?; done_ campaign $rc; echo $rc > campaign.exit
step item11
taskset -c $QF_CPUS $PY tools/item11_eer.py --negative-controls > logs/item11.log 2>&1
done_ item11 $?
step item11-noguard
bash tools/item11_noguard_control.sh > logs/item11-noguard.log 2>&1
done_ item11-noguard $?
echo CHAIN_A_DONE
