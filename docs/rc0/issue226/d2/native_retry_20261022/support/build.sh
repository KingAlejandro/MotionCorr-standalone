#!/usr/bin/env bash
set -Eeuo pipefail
W=/mnt/clathrin/alex-pr252-native-retry-20261022T150600Z
cd "$W"
trap 'rc=$?; date -u +%FT%TZ > logs/build.finished; printf "%s\n" "$rc" > logs/build.exit; exit "$rc"' EXIT
printf '%s\n' "$$" > logs/build.pid
date -u +%FT%TZ > logs/build.started
export PATH=/usr/local/cuda-12.8/bin:$PATH
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
exec 8>/tmp/motioncorr-build.lock
flock -n 8
sha256sum -c source.sha256
# Re-extract only this new scratch's incomplete preparation, after verified transfer.
tar -xzf source.tar.gz -C src
cd src
patch -p1 < ../support/native-receipts.patch
cd ..
run() {
    local name=$1; shift
    printf '%q ' "$@" >> logs/commands.txt; printf '\n' >> logs/commands.txt
    set +e
    "$@" > "logs/$name.log" 2>&1
    local rc=$?
    set -e
    printf '%s\n' "$rc" > "logs/$name.exit"
    return "$rc"
}
run configure cmake -S src -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3
run compile cmake --build build --target motioncorr cuda_local_admission patch_retry_admission patch_retry_state --parallel 2
run host-controls ctest --test-dir build -R '^(PatchRetryAdmission|PatchRetryState)$' --output-on-failure --parallel 1
sha256sum build/motioncorr build/cuda_local_admission build/patch_retry_admission build/patch_retry_state > logs/binaries.sha256
cp build/CMakeCache.txt logs/
cp build/CMakeFiles/motioncorr_core.dir/flags.make logs/core-flags.make
cp build/CMakeFiles/cuda_local_admission.dir/link.txt logs/admission-link.txt
