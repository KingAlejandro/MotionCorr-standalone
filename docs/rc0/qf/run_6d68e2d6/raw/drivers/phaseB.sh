#!/bin/bash
# QF phase B (single-GPU lane, GPU0 + CPUs 96-103): probes, items 9, 5+6, 7, 12 (single GPU), 13, 11.
# Starts after phaseA.done. Sentinel: phaseB.done
set -u
source /mnt/clathrin/alex-motioncorr-rc0/W-QF/env.sh
cd $QF_W
until [ -e phaseA.done ]; do sleep 30; done
PY=/home/alex/.mc-venv/bin/python3
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
step() { name=$1; shift; echo "== $name start $(date -u +%FT%TZ)"; "$@" > logs/$name.out 2>&1; rc=$?; echo "== $name rc=$rc end $(date -u +%FT%TZ) du=$(du -sh $QF_W 2>/dev/null | cut -f1)"; }
{
echo "phaseB start $(date -u +%FT%TZ)"
step probe_campaign_refusal taskset -c $QF_CPUS $PY tools/probe_campaign_refusal.py
step probe_matrix_fallback_witness taskset -c $QF_CPUS $PY tools/probe_matrix_fallback_witness.py
step probe_item12_dataset_grader taskset -c $QF_CPUS $PY tools/probe_item12_dataset_grader.py
step probe_multigpu_dryrun taskset -c $QF_CPUS $PY tools/probe_multigpu_dryrun.py
step mg_dryrun_GL taskset -c $QF_CPUS $PY tools/multigpu_publication.py --dry-run
step mg_dryrun_mixed taskset -c $QF_CPUS $PY tools/multigpu_publication.py --mixed --dry-run
for cfg in nvcomp cuda; do
  step item9_$cfg flock $QF_GPU_LOCK taskset -c $QF_CPUS $PY tools/run_compact_ingest_support_matrix.py --binary build-$cfg/motioncorr --device $QF_GPU_UUID --workdir matrix-$cfg --json matrix-$cfg.json
done
step item5_campaign taskset -c $QF_CPUS $PY tools/product_campaign.py
step item7_fallback178 taskset -c $QF_CPUS $PY tools/fallback178.py
step item7_fallback178_injected taskset -c $QF_CPUS $PY tools/fallback178_injected.py
step item12_single taskset -c $QF_CPUS $PY tools/item12_retry.py
step item13 bash tools/item13_mrc.sh
step probe_item13_exit bash tools/probe_item13_exit.sh
step item11 taskset -c $QF_CPUS $PY tools/item11_eer.py --negative-controls
step item11_noguard bash tools/item11_noguard_control.sh
echo "phaseB end $(date -u +%FT%TZ) src_status=$(git -C src status --porcelain | wc -l)"
} >> logs/phaseB.log 2>&1
echo done > phaseB.done
