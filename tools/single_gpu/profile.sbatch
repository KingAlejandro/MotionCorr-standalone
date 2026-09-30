#!/bin/bash
#SBATCH -p gpu-devel
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --exclusive
#SBATCH -t 04:00:00
#SBATCH -J mc-sgpu
#SBATCH -o /work4/scd/scarf1415/motioncorr/post128-sgpu-20261001/slurm-%j.out
set -euo pipefail
D=/work4/scd/scarf1415/motioncorr/post128-sgpu-20261001
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVR=/home/vol05/scarf1415/nvcomp-sdk
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$NVR/lib:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=6 TMPDIR=/tmp
cd "$D"
exec 9> "$D/campaign.lock"; flock -n 9
hostname >venue.txt; date -Is >>venue.txt
nvidia-smi --query-gpu=index,uuid,name,memory.total --format=csv >>venue.txt
nvidia-smi --query-compute-apps=pid,gpu_uuid,process_name --format=csv >>venue.txt
grep Cpus_allowed_list /proc/self/status >>venue.txt
lscpu >>venue.txt; cat /sys/kernel/mm/transparent_hugepage/enabled >>venue.txt
scontrol show job "$SLURM_JOB_ID" >>venue.txt
# Use six granted physical CPUs, chosen from the actual permitted set. The
# remaining allocation is reserved for the writer and measurements.
MASK=$(python3 - <<'PY'
import os
print(','.join(map(str,sorted(os.sched_getaffinity(0))[:8])))
PY
)
echo "runtime mask=$MASK" >>venue.txt
CM=(-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NVR" -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME")
cmake -S baseline-src -B baseline-build "${CM[@]}" >configure.log 2>&1
cmake --build baseline-build --parallel 8 >build.log 2>&1
sha256sum baseline-build/motioncorr >binary.sha256
cp -a baseline-src profile-src
python3 instrument_profile.py profile-src
cmake -S profile-src -B profile-build "${CM[@]}" >profile-configure.log 2>&1
cmake --build profile-build --parallel 8 >profile-build.log 2>&1
R=/work4/scd/scarf1415/motioncorr/i53-scarf/runroot
cd "$R"
sha256sum movies.star Movies/gain.mrc > "$D/inputs.sha256"
find -L Movies -name '*.tiff' -print0 | sort -z | xargs -0 sha256sum >> "$D/inputs.sha256"
ARGS=(--i movies.star --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 6 --max_io_threads 6 --ingest nvcomp)
for rep in 1 2 3; do
 mkdir -p "$D/baseline-r$rep"
 taskset -c "$MASK" /usr/bin/time -v "$D/baseline-build/motioncorr" "${ARGS[@]}" --o "$D/baseline-r$rep/" --ingest_witness "$D/baseline-r$rep.witness" > "$D/baseline-r$rep.log" 2>&1
done
mkdir -p "$D/profile-output"
taskset -c "$MASK" nsys profile --trace=cuda,nvtx,osrt --cuda-memory-usage=true --sample=none --cpuctxsw=none --force-overwrite=true --output="$D/profile" "$D/profile-build/motioncorr" "${ARGS[@]}" --o "$D/profile-output/" --ingest_witness "$D/profile.witness" > "$D/profile.log" 2>&1
nsys export --type=sqlite --force-overwrite=true --output="$D/profile.sqlite" "$D/profile.nsys-rep" > "$D/export.log" 2>&1
nsys stats --report cuda_api_sum,cuda_gpu_kern_sum,cuda_gpu_mem_time_sum,nvtx_sum --format csv "$D/profile.nsys-rep" > "$D/stats.csv" 2>&1
touch "$D/PROFILE_DONE"
# Root may send a bounded candidate test/benchmark script into this dedicated
# allocation. Never execute partial uploads. Release automatically on timeout.
for i in $(seq 1 120); do
 if [ -f "$D/CANDIDATE_READY" ]; then bash "$D/candidate.sh"; exit $?; fi
 sleep 30
done
