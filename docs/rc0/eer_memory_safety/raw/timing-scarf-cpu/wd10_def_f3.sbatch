#!/bin/bash
# Definitive pre-declared whole-job CPU timing design (#221 / RC0 D10): EMPIAR-10474 Falcon 3
# - Venue: SCARF exclusive CPU node (-p scarf --exclusive)
# - Workload: EMPIAR-10474 Falcon 3, config L (5x5), grouping 40, upsampling 1, --j 16 on CPUs 0-15
# - Design: 1 warmup per arm, N = 32 balanced pairs (16 AB + 16 BA interleaved), 12 AA null pairs
# - Exclusion rule: mcprof.py compare default (> 3 robust SDs; both raw all-pairs and outlier-filtered reported)
#SBATCH -p scarf
#SBATCH --nodes=1
#SBATCH --cpus-per-task=64
#SBATCH --exclusive
#SBATCH -t 01:30:00
#SBATCH -J wd10-f3
#SBATCH -o /work4/scd/scarf1415/W-D10/slurm-def-f3-%j.out

set -euo pipefail
unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES PYTHONOPTIMIZE
export OMP_NUM_THREADS=16
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

ROOT=/work4/scd/scarf1415/W-D10
OUT="$ROOT/def-f3-${SLURM_JOB_ID}"
W="/tmp/wd10-f3-${SLURM_JOB_ID}"
mkdir -p "$OUT" "$W/src-main" "$W/src-fix" "$W/data-f3/Movies"

exec > >(tee "$OUT/job.log") 2>&1

echo "=== 0. Provenance ==="
date -u +%FT%TZ
hostname
lscpu | grep -E "Model name|Socket|Thread|NUMA|CPU\(s\):" || true
cat /sys/kernel/mm/transparent_hugepage/enabled || true
echo "GLIBC_TUNABLES=${GLIBC_TUNABLES:-<unset>}"
cmake --version | head -1
g++ --version | head -1
python3 --version

tar -xzf "$ROOT/w-d10-main.tar.gz" -C "$W/src-main"
tar -xzf "$ROOT/w-d10-fix.tar.gz" -C "$W/src-fix"
echo "71ab841e69869b615555bb02f8f393db59c22d73" > "$W/src-main/SOURCE_COMMIT"
echo "97fb9fda5902f4bd5c2aab7c40ae4064637b5125" > "$W/src-fix/SOURCE_COMMIT"

for arm in main fix; do
  taskset -c 0-31 cmake -S "$W/src-$arm" -B "$W/build-$arm" \
    -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=OFF \
    > "$OUT/configure-$arm.log" 2>&1
  taskset -c 0-31 cmake --build "$W/build-$arm" -j 32 \
    > "$OUT/build-$arm.log" 2>&1
done
sha256sum "$W/build-main/motioncorr" "$W/build-fix/motioncorr" | tee "$OUT/binaries.sha256"

CORPUS=/work4/scd/scarf1415/mc-corpus-formats/data
cp -L "$CORPUS/EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-39-45.801_eer_data_4096x4096.eer" "$W/data-f3/Movies/movie1.eer"
cat << "STAR" > "$W/data-f3/movies.star"
# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 1.06 300 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/movie1.eer 1
STAR
cat "$W/data-f3/Movies/movie1.eer" > /dev/null
sha256sum "$W/data-f3/Movies/movie1.eer" | tee "$OUT/inputs.sha256"

MC_F3=(--use_own --dose_weighting --dose_per_frame 1.0 --patch_x 5 --patch_y 5
       --bfactor 150 --eer_grouping 40 --eer_upsampling 1
       --expected_frames 58 --seed 1 --skip_report_pdf --j 16)

echo "=== Definitive AB/BA (32 pairs: 16 AB + 16 BA, warmup 1) ==="
python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
  main="$W/build-main/motioncorr" fix="$W/build-fix/motioncorr" \
  --source main="$W/src-main" --source fix="$W/src-fix" \
  --commit main=71ab841e69869b615555bb02f8f393db59c22d73 \
  --commit fix=97fb9fda5902f4bd5c2aab7c40ae4064637b5125 \
  --data "$W/data-f3" --star movies.star --work "$OUT/e10474f3_ab32" \
  --cpus 0-15 --runner-cpus 16-19 --warmup 1 --pairs 32 --no-lock \
  -- "${MC_F3[@]}"

echo "=== Definitive AA Null (12 pairs, warmup 1) ==="
python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
  main="$W/build-main/motioncorr" main_null="$W/build-main/motioncorr" \
  --source main="$W/src-main" --source main_null="$W/src-main" \
  --commit main=71ab841e69869b615555bb02f8f393db59c22d73 \
  --commit main_null=71ab841e69869b615555bb02f8f393db59c22d73 \
  --data "$W/data-f3" --star movies.star --work "$OUT/e10474f3_aa12" \
  --cpus 0-15 --runner-cpus 16-19 --warmup 1 --pairs 12 --no-lock \
  -- "${MC_F3[@]}"

cat "$OUT/e10474f3_ab32/report.md"
cat "$OUT/e10474f3_aa12/report.md"
rm -rf "$W"
echo "DEF_F3_COMPLETE $(date -u +%FT%TZ)"
