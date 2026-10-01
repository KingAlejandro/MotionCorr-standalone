#!/bin/bash
#SBATCH -p gpu-devel
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --exclusive
#SBATCH -w gn0004
#SBATCH -t 02:00:00
#SBATCH -J mc-fft-sync
#SBATCH -o /work4/scd/scarf1415/motioncorr/post128-fft-sync-20261001/slurm-%j.out
set -euo pipefail
D=/work4/scd/scarf1415/motioncorr/post128-fft-sync-20261001
OLD=/work4/scd/scarf1415/motioncorr/post128-sgpu-20261001
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVR=/home/vol05/scarf1415/nvcomp-sdk
export PATH="$CUDA_HOME/bin:$PATH" LD_LIBRARY_PATH="$CUDA_HOME/lib64:$NVR/lib:${LD_LIBRARY_PATH:-}" OMP_NUM_THREADS=6 TMPDIR=/tmp
cd "$D"
exec 9> "$D/campaign.lock"; flock -n 9
trap 'date -Is > "$D/released.txt"; nvidia-smi --query-compute-apps=pid,gpu_uuid,process_name --format=csv,noheader > "$D/release-occupancy.txt"' EXIT
hostname >venue.txt;date -Is >>venue.txt
scontrol show job "$SLURM_JOB_ID" >>venue.txt
nvidia-smi --query-gpu=index,uuid,name,memory.total --format=csv >>venue.txt
nvidia-smi --query-compute-apps=pid,gpu_uuid,process_name --format=csv,noheader >occupancy-before.txt
if test -s occupancy-before.txt; then exit 3;fi
lscpu >>venue.txt;cat /sys/kernel/mm/transparent_hugepage/enabled >>venue.txt
grep Cpus_allowed_list /proc/self/status >>venue.txt
MASK=$(python3 - <<'PYMASK'
import os
assert set(range(8))<=os.sched_getaffinity(0),'Requested CPUs0-7 unavailable'
print('0-7')
PYMASK
)
printf '%s\n' "$MASK" >cpu-mask.txt
nvidia-smi -i 0 --query-gpu=uuid --format=csv,noheader >gpu-uuid.txt
CM=(-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NVR" -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME")
git clone --no-hardlinks "$OLD/baseline-src" baseline-src >clone.log 2>&1
git -C baseline-src checkout c499b1d3bf1cceec5c3b194f356844d6f493e7f2 >>clone.log 2>&1
cmake -S baseline-src -B baseline-build "${CM[@]}" >baseline-configure.log 2>&1
taskset -c "$MASK" cmake --build baseline-build --parallel 8 >baseline-build.log 2>&1
sha256sum baseline-build/motioncorr >baseline-binary.sha256
taskset -c "$MASK" ctest --test-dir baseline-build --output-on-failure --timeout 900 >baseline-ctest.log 2>&1
touch BASELINE_DONE
# Bounded wait for frozen reviewed source; no partial uploads are executed.
for n in $(seq 1 60);do
 if test -f CANDIDATE_READY;then bash candidate.sh;exit $?;fi
 sleep 30
done
exit 4
