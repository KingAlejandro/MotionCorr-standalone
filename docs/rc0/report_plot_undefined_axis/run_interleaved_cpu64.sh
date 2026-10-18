#!/bin/bash
# Pre-specified Interleaved Definitive Paired Whole-Job CPU Comparison for Issue #229 (D13 / D14)
#
# Declared Design (fixed before execution; written to rule.txt & design.json before warmup):
#   - Venue & Lock:     cpu64 (small-refmac-machine, 2x AMD EPYC 7763 64-Core, THP madvise),
#                       holding /tmp/motioncorr-cpu64-bench.lock via flock for the entire window.
#   - CPU Affinity:     Payload pinned to CPUs 48-55 (single 8-core CCD on NUMA node 1, --j 8,
#                       OMP_NUM_THREADS=8); driver/sampler pinned to CPUs 56-59.
#   - Environment:      GLIBC_TUNABLES unset, OMP_PROC_BIND/OMP_PLACES unset, OPENBLAS_NUM_THREADS=1.
#   - Binaries:         Matched Release (-O3 -DNDEBUG -std=gnu++17 -fopenmp, -DCUDA=OFF):
#                         A  (main 1afa03b57afbae42138ee30c3545b57b5a74c321):
#                           /home/ubuntu/mc-w-d13/build-main/motioncorr
#                           sha256 307a030b03785201342a57c4d8adae14120d87676fa6bec7e62f8959d5b03a35
#                         B  (fix  b82d25f4dda6bca746e4206fed1272851cc6a5ce):
#                           /home/ubuntu/mc-w-d13/build-fix/motioncorr
#                           sha256 68dc7ac11049bb15be3caa90af10adb6c7bb7e44b752d797080b9ca1a79d96f9
#                         A' (same main binary under directory tag A2, safe for shell/gs paths)
#   - Workload:         2-movie tutorial subset (movies2.star: 20170629_00021_frameImage.tiff,
#                       20170629_00022_frameImage.tiff + gain.mrc, staged in /dev/shm tmpfs),
#                       sized from recorded pilot raw/cpu64_pilot/pilot_summary.json (no new pilot).
#   - Payload Options:  --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
#                       --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8
#                       (report generation ON: no --skip_report_pdf; writes logfile.pdf + EPS).
#   - Interleaved Order:
#       1. Warm-up: 1 run of A, 1 run of B (discarded).
#       2. Definitive: 16 comparison blocks [AB, BA] (N = 32 pairs: 16 AB / 16 BA).
#          After every k = 2-nd comparison block (blocks 2, 4, 6, 8, 10, 12, 14, 16),
#          run 1 null block [AA', A'A] (N_null = 16 null pairs: 8 AA' / 8 A'A).
#          The last null block follows the last comparison block.
#   - Exclusions:
#       Discard a pair only for a non-zero exit (rc != 0), missing MRC/PDF products, unverified
#       executable path, CPU affinity mismatch (!= [48..55]), or foreign CPU > 0.25 cores on
#       lane 48-55; rerun a discarded pair immediately in the same position and order, up to
#       3 attempts.

set -euo pipefail

unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES PYTHONOPTIMIZE
export PATH=/home/ubuntu/.mc-venv/bin:$PATH
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=1

W=/home/ubuntu/mc-w-d13
SHM=/dev/shm/mc-w-d13-interleaved
OUT=$W/interleaved_definitive
rm -rf "$SHM" "$OUT"
mkdir -p "$SHM/data/Movies" "$SHM/scratch" "$OUT"

exec > >(tee "$OUT/interleaved.log") 2>&1

echo "=== 0. Interleaved Definitive Run Provenance (cpu64) ==="
date -u +%FT%TZ
hostname
uname -a
lscpu | grep -E "Model name|CPU\(s\):|NUMA|Socket|Thread"
cat /sys/kernel/mm/transparent_hugepage/enabled
echo "GLIBC_TUNABLES=${GLIBC_TUNABLES:-<unset>}"
cmake --version | head -1
g++ --version | head -1
gs --version
python3 --version
sha256sum "$W/build-main/motioncorr" "$W/build-fix/motioncorr" | tee "$OUT/binaries.sha256"
stat -c "%y (%Y) %n" "$W/run_interleaved_cpu64.sh" "$W/wd13_interleaved_pairs.py" | tee "$OUT/script_timestamps.txt"

# Stage 2-movie tutorial subset in /dev/shm tmpfs
SRC_MOV=/home/ubuntu/mc-corpus-186/data/tutorial/Movies
cp -L /home/ubuntu/mc-corpus-186/corpus/tutorial/gain.mrc "$SHM/data/gain.mrc"
cp -L "$SRC_MOV/20170629_00021_frameImage.tiff" "$SHM/data/Movies/20170629_00021_frameImage.tiff"
cp -L "$SRC_MOV/20170629_00022_frameImage.tiff" "$SHM/data/Movies/20170629_00022_frameImage.tiff"

cat << 'STAR' > "$SHM/data/movies2.star"
# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 0.885 200 1.4 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/20170629_00021_frameImage.tiff 1
Movies/20170629_00022_frameImage.tiff 1
STAR

( cd "$SHM/data" && sha256sum movies2.star gain.mrc Movies/* ) | tee "$OUT/inputs.sha256"

MC_ARGS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
         --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8)

echo "=== Waiting for /tmp/motioncorr-cpu64-bench.lock $(date -u +%FT%TZ) ==="
(
  exec 9>/tmp/motioncorr-cpu64-bench.lock
  flock 9
  echo "=== Acquired /tmp/motioncorr-cpu64-bench.lock $(date -u +%FT%TZ) ==="

  python3 "$W/wd13_interleaved_pairs.py" \
    --name tutorial_2mov \
    --a "$W/build-main/motioncorr" \
    --b "$W/build-fix/motioncorr" \
    --data "$SHM/data" \
    --star movies2.star \
    --cpus 48-55 \
    --runner-cpus 56-59 \
    --src "$W/src-fix" \
    --pilot-summary "$W/pilot/pilot_summary.json" \
    --out "$OUT" \
    --scratch "$SHM/scratch" \
    -- "${MC_ARGS[@]}"
)

rm -rf "$SHM"
stat -c "%y (%Y) %n" "$OUT/rule.txt" "$OUT/design.json" "$OUT/declared_timestamps.json" | tee -a "$OUT/script_timestamps.txt"
echo "INTERLEAVED_CPU64_COMPLETE $(date -u +%FT%TZ)"
