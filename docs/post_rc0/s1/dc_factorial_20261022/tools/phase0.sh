#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# #262 Phase 0 on 4GPUs (FREEZE.md): stage oracle (CPU and CUDA builds), restoring
# mutants, existing focused tests under every arm. GPU2 only, lock held nonblocking
# from admission through the final health check. Usage: phase0.sh ROOT
set -u
ROOT=$1; P=$ROOT/phase0; mkdir -p "$P"
UUID=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64
health() { { date -u +%FT%TZ; nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu,ecc.errors.uncorrected.volatile.total --format=csv,noheader; nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader; } > "$P/$1.txt" 2>&1; }
run() { local name=$1; shift; ( cd "$P" && taskset -c 13 "$@" ) > "$P/$name.log" 2>&1; local rc=$?; echo "$rc" > "$P/$name.exit"; echo "$name rc=$rc"; }
exec 8>>/tmp/motioncorr-gpu2-correctness.lock
flock -n 8 || { echo "GPU2 lock busy" > "$P/lock.txt"; exit 75; }
health gpu-admission
if grep -q "$UUID" <(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader); then echo "GPU2 busy" > "$P/busy.txt"; exit 75; fi
C=$ROOT/b/cpu-exp; G=$ROOT/b/cuda-exp
run stage-cpu-build env CUDA_VISIBLE_DEVICES= $C/experiment_ccf_dc_stage --json $P/stage-cpu-build.json
export CUDA_VISIBLE_DEVICES=$UUID CUDA_DEVICE_ORDER=PCI_BUS_ID
run stage-cuda-build $G/experiment_ccf_dc_stage --json $P/stage-cuda-build.json
for m in cpu_restore cpu_wrong_bin cpu_stage_swap; do
  run mutant-cpu-build-$m env CUDA_VISIBLE_DEVICES= $C/experiment_ccf_dc_stage_$m --expect-failure
done
for m in cpu_restore cpu_wrong_bin cpu_stage_swap cuda_single_restore cuda_batched_restore cuda_single_resident cuda_single_stage_swap; do
  run mutant-cuda-build-$m $G/experiment_ccf_dc_stage_$m --expect-failure
done
for arm in none global local both; do
  for t in cuda_patch_batch cuda_hermitian_ccf cuda_peak_fit patch_retry_state; do
    run existing-$t-$arm env MC_EXPERIMENT_CCF_DC_ARM=$arm $G/$t
  done
  run existing-cpu_patch_retry_state-$arm env CUDA_VISIBLE_DEVICES= MC_EXPERIMENT_CCF_DC_ARM=$arm $C/patch_retry_state
done
# Fail-closed contract: an experiment binary without an arm must abort, not run.
# Expected: abort (exit 134) before any output on CPU and CUDA builds.
V=$ROOT/v2fixtures
for b in cpu cuda; do
  B=$ROOT/b/$b-exp/motioncorr; X=(); [ $b = cuda ] && X=(--gpu 0)
  for v in unset Both; do
    E=(env MC_EXPERIMENT_CCF_DC_ARM=$v); [ $v = unset ] && E=(env -u MC_EXPERIMENT_CCF_DC_ARM)
    ( cd $V && taskset -c 13 "${E[@]}" $B --i zero.star --o $P/failclosed-$b-$v/ --use_own --j 1 --patch_x 1 --patch_y 1 \
        --bin_factor 1 --seed 1 --skip_defect --skip_logfile "${X[@]}" ) > $P/failclosed-$b-$v.log 2>&1
    echo $? > $P/failclosed-$b-$v.exit
  done
done
health gpu-final
date -u +%FT%TZ > "$P/done.txt"
