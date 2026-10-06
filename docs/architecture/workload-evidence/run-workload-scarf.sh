#!/usr/bin/env bash
set -euo pipefail
test -n "${SLURM_JOB_ID:-}"
cd /work4/scd/scarf1415/motioncorr/issue142-architecture-20261002
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=4
mkdir -p workload-evidence
{
    date -Is; hostname; printf 'CUDA_VISIBLE_DEVICES=%s\n' "${CUDA_VISIBLE_DEVICES:-}"
    nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.used --format=csv
    scontrol show job "$SLURM_JOB_ID"; grep Cpus_allowed_list /proc/self/status
    sha256sum compressed-fix.patch workload_matrix.py
} > workload-evidence/venue.txt
cmake -S fix-src -B fix-build -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=OFF -DBUILD_TESTING=ON > workload-evidence/configure.log 2>&1
cmake --build fix-build --parallel 4 > workload-evidence/build.log 2>&1
ctest --test-dir fix-build --output-on-failure -j 1 > workload-evidence/ctest.log 2>&1
sha256sum fix-build/motioncorr fix-build/runner_numerics > workload-evidence/binary.sha256
python3 fix-src/tools/architecture/workload_matrix.py --binary fix-build/motioncorr \
    --helper fix-build/runner_numerics --output workload-evidence/matrix --gpu \
    > workload-evidence/matrix.log 2>&1
date -Is > workload-evidence/DONE
