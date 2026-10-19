#!/bin/bash
# QF phase C: supplementary m0_swapped_nx128 run (single-GPU lane), then the multi-GPU window:
# item 8 (G,L and mixed) and the item 12 dataset part. multigpu_step.sh takes all four gpuN-correctness
# locks (ascending) and the bench lock, and waits for no compute process on any GPU. Sentinel: phaseC.done
set -u
source /mnt/clathrin/alex-motioncorr-rc0/W-QF/env.sh
cd $QF_W
until [ -e phaseB.done ]; do sleep 30; done
PY=/home/alex/.mc-venv/bin/python3
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
step() { name=$1; shift; echo "== $name start $(date -u +%FT%TZ)"; "$@" > logs/$name.out 2>&1; rc=$?; echo "== $name rc=$rc end $(date -u +%FT%TZ) du=$(du -sh $QF_W 2>/dev/null | cut -f1)"; }
{
echo "phaseC start $(date -u +%FT%TZ)"
step supp_m0_nx128 taskset -c $QF_CPUS $PY drivers/supp_m0_nx128.py
echo "occupancy before window: $(nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader | wc -l) compute processes"
step item8_GL bash tools/multigpu_step.sh --configs G,L
step item8_mixed bash tools/multigpu_step.sh --mixed
step item12_dataset bash tools/multigpu_step.sh --driver item12_retry.py --dataset
echo "phaseC end $(date -u +%FT%TZ) src_status=$(git -C src status --porcelain | wc -l) HEAD=$(git -C src rev-parse HEAD)"
} >> logs/phaseC.log 2>&1
echo done > phaseC.done
