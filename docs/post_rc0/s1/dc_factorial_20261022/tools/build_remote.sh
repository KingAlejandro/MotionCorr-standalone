#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# #262 four-arm builds on 4GPUs. Usage: build_remote.sh ROOT SHA
# Takes /tmp/motioncorr-build.lock nonblocking (exit 75 on contention, no wait),
# builds four Release trees from ROOT/src (git archive of SHA) with --parallel 2
# under the inherited CPU mask, and writes per-step exits and binary hashes.
set -u
ROOT=$1; SHA=$2; LOG=$ROOT/build; mkdir -p "$LOG"
exec 9>>/tmp/motioncorr-build.lock
if ! flock -n 9; then echo "build lock busy" > "$LOG/lock.txt"; exit 75; fi
date -u +%FT%TZ > "$LOG/lock-acquired.txt"
PY=/home/alex/.mc-venv/bin/python3
export PATH=/usr/local/cuda-12.8/bin:$PATH
step() { local name=$1; shift; "$@" > "$LOG/$name.log" 2>&1; local rc=$?; echo "$rc" > "$LOG/$name.exit"; echo "$name rc=$rc"; return $rc; }
common=(-DCMAKE_BUILD_TYPE=Release -DUSE_NVCOMP=OFF -DPython3_EXECUTABLE=$PY)
step cfg-cpu-exp  cmake -S "$ROOT/src" -B "$ROOT/b/cpu-exp"  "${common[@]}" -DCUDA=OFF -DBUILD_TESTING=ON -DMC_EXPERIMENT_CCF_DC=ON || exit 1
step bld-cpu-exp  cmake --build "$ROOT/b/cpu-exp" --parallel 2 --target motioncorr experiment_ccf_dc_stage \
    experiment_ccf_dc_stage_cpu_restore experiment_ccf_dc_stage_cpu_wrong_bin experiment_ccf_dc_stage_cpu_stage_swap patch_retry_state || exit 1
step cfg-cpu-plain cmake -S "$ROOT/src" -B "$ROOT/b/cpu-plain" "${common[@]}" -DCUDA=OFF -DBUILD_TESTING=OFF || exit 1
step bld-cpu-plain cmake --build "$ROOT/b/cpu-plain" --parallel 2 --target motioncorr || exit 1
step cfg-cuda-exp  cmake -S "$ROOT/src" -B "$ROOT/b/cuda-exp" "${common[@]}" -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON -DMC_EXPERIMENT_CCF_DC=ON || exit 1
step bld-cuda-exp  cmake --build "$ROOT/b/cuda-exp" --parallel 2 --target motioncorr experiment_ccf_dc_stage \
    experiment_ccf_dc_stage_cpu_restore experiment_ccf_dc_stage_cpu_wrong_bin experiment_ccf_dc_stage_cpu_stage_swap \
    experiment_ccf_dc_stage_cuda_single_restore experiment_ccf_dc_stage_cuda_batched_restore \
    experiment_ccf_dc_stage_cuda_single_resident experiment_ccf_dc_stage_cuda_single_stage_swap \
    cuda_patch_batch cuda_hermitian_ccf cuda_peak_fit patch_retry_state || exit 1
step cfg-cuda-plain cmake -S "$ROOT/src" -B "$ROOT/b/cuda-plain" "${common[@]}" -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=OFF || exit 1
step bld-cuda-plain cmake --build "$ROOT/b/cuda-plain" --parallel 2 --target motioncorr || exit 1
find "$ROOT/b" -maxdepth 2 -type f -perm -u+x \( -name 'motioncorr' -o -name 'experiment_ccf_dc_stage*' -o -name 'cuda_*' -o -name 'patch_retry_state' \) \
    -exec sha256sum {} + | sort -k2 > "$LOG/binary-hashes.txt"
{ gcc --version | head -1; cmake --version | head -1; nvcc --version | tail -2; } > "$LOG/toolchain.txt" 2>&1
for b in cpu-exp cpu-plain cuda-exp cuda-plain; do grep -E "CMAKE_BUILD_TYPE|CMAKE_CXX_FLAGS_RELEASE|CMAKE_CUDA_FLAGS_RELEASE|MC_EXPERIMENT_CCF_DC|^CUDA:|USE_NVCOMP|CMAKE_CUDA_ARCHITECTURES" "$ROOT/b/$b/CMakeCache.txt" > "$LOG/cache-$b.txt"; done
date -u +%FT%TZ > "$LOG/done.txt"
