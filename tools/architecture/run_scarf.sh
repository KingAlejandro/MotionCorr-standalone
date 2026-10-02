#!/usr/bin/env bash
# Submit from an empty campaign directory containing a clone named src:
# sbatch -p gpu-devel --gres=gpu:1 --cpus-per-task=4 --exclusive -t 00:30:00 src/tools/architecture/run_scarf.sh
set -euo pipefail
test -n "${SLURM_JOB_ID:-}"  # Never run this on a login node.
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=4
mkdir -p evidence
{
    date -Is; hostname; git -C src rev-parse HEAD
    nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu --format=csv
    nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv
    nvcc --version; cmake --version; c++ --version
    scontrol show job "$SLURM_JOB_ID"
    grep Cpus_allowed_list /proc/self/status
} > evidence/venue.txt
cmake -S src -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=OFF -DBUILD_TESTING=ON \
    -DARCHITECTURE_BENCHMARKS=ON > evidence/configure.log 2>&1
cmake --build build --parallel 4 > evidence/build.log 2>&1
sha256sum build/movie_fft_bench build/motioncorr > evidence/binaries.sha256
ctest --test-dir build --output-on-failure -j 1 > evidence/ctest.log 2>&1 || touch evidence/CTEST_FAILED
# Shapes include a tail batch and an odd dimension. Large cases are bounded
# below 40 GB including the extra reference buffers used only by this harness.
for shape in '256 256 24' '256 256 160' '512 511 25' '1024 768 24' \
             '3710 3838 24' '4096 4096 24' '4096 4096 80'; do
    read -r x y f <<< "$shape"
    build/movie_fft_bench "$x" "$y" "$f" 7 > "evidence/fft-${x}-${y}-${f}.jsonl" \
        2> "evidence/fft-${x}-${y}-${f}.err"
done
date -Is > evidence/DONE
