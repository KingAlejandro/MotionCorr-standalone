#!/bin/bash
# Pilot (6 pairs) + Definitive pre-declared GPU timing design (#221 / RC0 D10):
# - Venue: SCARF exclusive GPU node (-p gpu --gres=gpu:1 --exclusive --constraint=scarf23)
# - Workload: EMPIAR-12963 with EER gain, config L (5x5), CUDA EER compact route (--gpu 0 --ingest compact), --j 8
# - Pilot: 6 pairs (3 AB + 3 BA), recorded separately in pilot_e12963_cuda
# - Definitive: 1 warmup per arm, N = 32 balanced pairs (16 AB + 16 BA interleaved), 12 AA null pairs
# - Exclusion rule: mcprof.py compare default (> 3 robust SDs; both raw all-pairs and outlier-filtered reported)
#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 01:30:00
#SBATCH -J mc-wd10-gpu
#SBATCH -o /work4/scd/scarf1415/W-D10/slurm-gpu-%j.out

set -euo pipefail

export CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES PYTHONOPTIMIZE
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

ROOT=/work4/scd/scarf1415/W-D10
OUT="$ROOT/gpu-results-${SLURM_JOB_ID}"
W="/tmp/wd10-gpu-${SLURM_JOB_ID}"
mkdir -p "$OUT" "$W/src-main" "$W/src-fix"

exec > >(tee "$OUT/job.log") 2>&1

echo "=== 0. Provenance ==="
date -u +%FT%TZ
hostname
lscpu | grep -E "Model name|Socket|Thread|NUMA|CPU\(s\):" || true
cat /sys/kernel/mm/transparent_hugepage/enabled || true
echo "GLIBC_TUNABLES=${GLIBC_TUNABLES:-<unset>}"
nvidia-smi --query-gpu=index,name,uuid,memory.total --format=csv
GPU_UUID=$(nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1 | tr -d "[:space:]")
export CUDA_VISIBLE_DEVICES="$GPU_UUID"
echo "Pinned CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
nvcc --version
cmake --version | head -1
g++ --version | head -1
python3 --version

echo "=== 1. Unpack sources & build Release CUDA binaries ==="
tar -xzf "$ROOT/w-d10-main.tar.gz" -C "$W/src-main"
tar -xzf "$ROOT/w-d10-fix.tar.gz" -C "$W/src-fix"
echo "71ab841e69869b615555bb02f8f393db59c22d73" > "$W/src-main/SOURCE_COMMIT"
echo "97fb9fda5902f4bd5c2aab7c40ae4064637b5125" > "$W/src-fix/SOURCE_COMMIT"

for arm in main fix; do
  cmake -S "$W/src-$arm" -B "$W/build-$arm" \
    -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 \
    -DUSE_NVCOMP=OFF -DBUILD_TESTING=OFF \
    -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME" \
    > "$OUT/configure-$arm.log" 2>&1
  cmake --build "$W/build-$arm" -j 8 > "$OUT/build-$arm.log" 2>&1
done
sha256sum "$W/build-main/motioncorr" "$W/build-fix/motioncorr" | tee "$OUT/binaries.sha256"

echo "=== 2. Stage EER inputs node-local & warm page cache ==="
CORPUS=/work4/scd/scarf1415/mc-corpus-formats/data
mkdir -p "$W/data-12963/Movies"
cp -L "$CORPUS/EMPIAR-12963/data/EMPIAR-Deposition/RawMicrographs/Images-Disc1/GridSquare_4650264/Data/FoilHole_4674725_Data_4659374_4659376_20230406_014501_EER.eer" "$W/data-12963/Movies/movie1.eer"
cp -L "$CORPUS/EMPIAR-12963/data/EMPIAR-Deposition/GainReference/20230326_221855_EER_GainReference.gain" "$W/data-12963/gain.gain"

cat << "STAR" > "$W/data-12963/movies.star"
# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 0.97 300 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/movie1.eer 1
STAR

cat "$W/data-12963/Movies/movie1.eer" "$W/data-12963/gain.gain" > /dev/null
sha256sum "$W/data-12963/Movies/movie1.eer" "$W/data-12963/gain.gain" | tee "$OUT/inputs.sha256"

MC_12963=(--use_own --gpu 0 --ingest compact --dose_weighting --dose_per_frame 1.282051282051282
          --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.gain --eer_grouping 49
          --eer_upsampling 1 --expected_frames 39 --seed 1 --skip_report_pdf --j 8)

echo "=== 3. Pilot (6 pairs: 3 AB + 3 BA, recorded separately) ==="
python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
  main="$W/build-main/motioncorr" fix="$W/build-fix/motioncorr" \
  --source main="$W/src-main" --source fix="$W/src-fix" \
  --commit main=71ab841e69869b615555bb02f8f393db59c22d73 \
  --commit fix=97fb9fda5902f4bd5c2aab7c40ae4064637b5125 \
  --data "$W/data-12963" --star movies.star --work "$OUT/pilot_e12963_cuda" \
  --cpus 0-7 --warmup 1 --pairs 6 --no-lock \
  -- "${MC_12963[@]}"

echo "=== 4. Definitive CUDA compact route paired timing: e12963 (32 AB/BA + 12 AA null) ==="
python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
  main="$W/build-main/motioncorr" fix="$W/build-fix/motioncorr" \
  --source main="$W/src-main" --source fix="$W/src-fix" \
  --commit main=71ab841e69869b615555bb02f8f393db59c22d73 \
  --commit fix=97fb9fda5902f4bd5c2aab7c40ae4064637b5125 \
  --data "$W/data-12963" --star movies.star --work "$OUT/def_e12963_cuda_ab32" \
  --cpus 0-7 --warmup 1 --pairs 32 --no-lock \
  -- "${MC_12963[@]}"

python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
  main="$W/build-main/motioncorr" main_null="$W/build-main/motioncorr" \
  --source main="$W/src-main" --source main_null="$W/src-main" \
  --commit main=71ab841e69869b615555bb02f8f393db59c22d73 \
  --commit main_null=71ab841e69869b615555bb02f8f393db59c22d73 \
  --data "$W/data-12963" --star movies.star --work "$OUT/def_e12963_cuda_aa12" \
  --cpus 0-7 --warmup 1 --pairs 12 --no-lock \
  -- "${MC_12963[@]}"

cat "$OUT/pilot_e12963_cuda/report.md"
cat "$OUT/def_e12963_cuda_ab32/report.md"
cat "$OUT/def_e12963_cuda_aa12/report.md"
rm -rf "$W"
echo "SCARF_GPU_TIMING_COMPLETE $(date -u +%FT%TZ)"
