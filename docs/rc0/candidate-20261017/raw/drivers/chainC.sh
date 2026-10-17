#!/bin/bash
# RC0 candidate multi-GPU window: started only after lanes A and B have finished.
# multigpu_step.sh takes gpu0..gpu3 correctness locks (ascending) and then the bench lock, and waits until no
# compute process is on any GPU. CPU budget: 96-103 + 104-111 (the two candidate lanes' CPUs).
# Item 8 (G,L: s0, w1, w2, w4; mixed: w1, w2) and item 12 dataset part (GPU0 + GPU1, asymmetric fault on GPU1).
set -u
cd /mnt/clathrin/alex-motioncorr-rc0/W-RC0-CAND || exit 90
. ./env-laneA.sh
export QF_MG_CPU_A=96-103 QF_MG_CPU_B=104-111 QF_MG_W1_GPU=0
export QF_DATASET_GPU2_UUID=GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d QF_DATASET_CPUS2=104-111
step() { echo "=== $1 start $(date -u +%FT%TZ)"; }
done_() { echo "=== $1 rc=$2 end $(date -u +%FT%TZ)"; }
until grep -q CHAIN_A_DONE logs/chainA.out 2>/dev/null && grep -q CHAIN_B_DONE logs/chainB.out 2>/dev/null; do sleep 60; done
step multigpu-dryrun
/home/alex/.mc-venv/bin/python3 tools/multigpu_publication.py --configs G,L --dry-run > logs/multigpu-dryrun.txt 2>&1
/home/alex/.mc-venv/bin/python3 tools/multigpu_publication.py --mixed --dry-run >> logs/multigpu-dryrun.txt 2>&1
done_ multigpu-dryrun $?
step multigpu-GL; bash tools/multigpu_step.sh --configs G,L > logs/multigpu-GL.log 2>&1; done_ multigpu-GL $?
step multigpu-mixed; bash tools/multigpu_step.sh --mixed > logs/multigpu-mixed.log 2>&1; done_ multigpu-mixed $?
step item12-dataset; bash tools/multigpu_step.sh --driver item12_retry.py --dataset > logs/item12-dataset.log 2>&1; done_ item12-dataset $?
echo CHAIN_C_DONE
