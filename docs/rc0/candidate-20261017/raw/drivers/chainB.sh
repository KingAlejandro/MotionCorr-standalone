#!/bin/bash
# RC0 candidate lane B: GPU1 GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d, CPUs 104-111, gpu1-correctness lock.
# Runs audited QF runbook items with the committed tools (unchanged). Correctness only, no timing claims.
# Order: item 1 (CTest CPU) -> item 3 (CTest CUDA+nvCOMP) -> item 13 -> item 12 (single GPU)
#        -> item 7 (#178), started only after lane A's campaign has finished, because product_campaign.py
#           and fallback178*.py both rebuild $QF_W/dataroot and $QF_W/inputs/<family> symlinks.
set -u
cd /mnt/clathrin/alex-motioncorr-rc0/W-RC0-CAND || exit 90
. ./env-laneB.sh
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
PY=/home/alex/.mc-venv/bin/python3
step() { echo "=== $1 start $(date -u +%FT%TZ)"; }
done_() { echo "=== $1 rc=$2 end $(date -u +%FT%TZ)"; }
step ctest-cpu; bash tools/run_ctest.sh cpu; done_ ctest-cpu "$(cat ctest-cpu.exit 2>/dev/null || echo none)"
step ctest-nvcomp; bash tools/run_ctest.sh nvcomp; done_ ctest-nvcomp "$(cat ctest-nvcomp.exit 2>/dev/null || echo none)"
step item13; bash tools/item13_mrc.sh > logs/item13.log 2>&1; done_ item13 $?
step item12; taskset -c $QF_CPUS $PY tools/item12_retry.py > logs/item12.log 2>&1; done_ item12 $?
until [ -f campaign.exit ]; do sleep 60; done
step fallback178; taskset -c $QF_CPUS $PY tools/fallback178.py > logs/fallback178.log 2>&1; done_ fallback178 $?
step fallback178-injected; taskset -c $QF_CPUS $PY tools/fallback178_injected.py > logs/fallback178-injected.log 2>&1; done_ fallback178-injected $?
echo CHAIN_B_DONE
