#!/bin/bash
# Full Issue #26 measurement series. Run INSIDE the flock.
set -u
cd /home/ubuntu/mc-issue26
R=/home/ubuntu/mc-issue26/results; mkdir -p $R
BT=/home/ubuntu/mc-issue26/src-3e3a19679337d3de61327c02eef1a2947cf13517/build-timing/motioncorr
BR=/home/ubuntu/mc-issue26/src-3e3a19679337d3de61327c02eef1a2947cf13517/build-rel/motioncorr
CT=/home/ubuntu/mc-issue26/src-cand/build-timing/motioncorr
CR=/home/ubuntu/mc-issue26/src-cand/build-rel/motioncorr
say(){ echo; echo "################ $* ################"; date -u +%FT%TZ; }

say "ARM A: baseline, 5x5 patches, default (unbound) affinity"
unset OMP_PROC_BIND OMP_PLACES MC26_NUMACTL
python3 bench26.py --binary $BT --patch 5 --threads 1,2,4,8,16 --reps 3 \
  --label A_patch5x5_unbound --out $R/A_patch5x5_unbound.json --max-load 4.2 --settle-timeout 120

say "ARM B: baseline, 5x5 patches, OMP_PROC_BIND=spread OMP_PLACES=cores"
export OMP_PROC_BIND=spread OMP_PLACES=cores
python3 bench26.py --binary $BT --patch 5 --threads 1,2,4,8,16 --reps 3 \
  --label B_patch5x5_spread --out $R/B_patch5x5_spread.json --max-load 4.2 --settle-timeout 120
unset OMP_PROC_BIND OMP_PLACES

say "ARM C: baseline, global-only (1x1), default affinity"
python3 bench26.py --binary $BT --patch 1 --threads 1,2,4,8,16 --reps 2 \
  --label C_global_unbound --out $R/C_global_unbound.json --max-load 4.2 --settle-timeout 120

say "ARM D: baseline, 5x5, numactl --cpunodebind=0 --membind=0 (single NUMA node)"
export MC26_NUMACTL="numactl --cpunodebind=0 --membind=0"
python3 bench26.py --binary $BT --patch 5 --threads 8,16 --reps 2 \
  --label D_patch5x5_numalocal --out $R/D_patch5x5_numalocal.json --max-load 4.2 --settle-timeout 120
unset MC26_NUMACTL

say "ARM E: paired base-vs-candidate, global-only, j=1"
python3 paired_ab.py --base $BR --cand $CR --j 1 --pairs 6 \
  --cfg "--patch_x 1 --patch_y 1" --label E_global_j1 --out $R/E_pab_global_j1.json

say "ARM F: paired base-vs-candidate, global-only, j=8"
python3 paired_ab.py --base $BR --cand $CR --j 8 --pairs 6 \
  --cfg "--patch_x 1 --patch_y 1" --label F_global_j8 --out $R/F_pab_global_j8.json

say "ARM G: paired base-vs-candidate, 5x5 (change must be a no-op), j=8"
python3 paired_ab.py --base $BR --cand $CR --j 8 --pairs 4 \
  --cfg "--patch_x 5 --patch_y 5" --label G_patch5x5_j8 --out $R/G_pab_patch5x5_j8.json

say "ARM H: whole-dataset throughput, baseline, global-only, 16-core budget"
python3 throughput.py --binary $BR --cfg "--patch_x 1 --patch_y 1" \
  --configs 1x16,2x8,4x4,8x2 --label H_base_global --out $R/H_tp_base_global.json

say "ARM I: whole-dataset throughput, candidate, global-only, 16-core budget"
python3 throughput.py --binary $CR --cfg "--patch_x 1 --patch_y 1" \
  --configs 1x16,4x4 --label I_cand_global --out $R/I_tp_cand_global.json

say "ARM J: whole-dataset throughput, baseline, 5x5, 16-core budget"
python3 throughput.py --binary $BR --cfg "--patch_x 5 --patch_y 5" \
  --configs 1x16,4x4 --label J_base_patch5x5 --out $R/J_tp_base_patch5x5.json

say "ARM K: throughput with affinity, baseline, global-only"
python3 throughput.py --binary $BR --cfg "--patch_x 1 --patch_y 1" \
  --configs 1x16,4x4 --bind "spread:cores" --label K_base_global_spread \
  --out $R/K_tp_base_global_spread.json

say "SERIES COMPLETE"
