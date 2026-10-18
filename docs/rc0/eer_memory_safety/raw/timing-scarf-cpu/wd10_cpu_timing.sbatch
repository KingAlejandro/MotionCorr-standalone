#!/bin/bash
#SBATCH -p scarf
#SBATCH --nodes=1
#SBATCH --cpus-per-task=64
#SBATCH --exclusive
#SBATCH -t 01:30:00
#SBATCH -J mc-wd10-cpu
#SBATCH -o /work4/scd/scarf1415/W-D10/slurm-cpu-%j.out

set -euo pipefail

unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES PYTHONOPTIMIZE
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

ROOT=/work4/scd/scarf1415/W-D10
OUT="$ROOT/cpu-results-${SLURM_JOB_ID}"
W="/tmp/wd10-cpu-${SLURM_JOB_ID}"
mkdir -p "$OUT" "$W/src-main" "$W/src-fix" "$W/src-main-helper"

exec > >(tee "$OUT/job.log") 2>&1

echo "=== 0. Provenance ==="
date -u +%FT%TZ
hostname
lscpu | grep -E "Model name|Socket|Thread|NUMA|CPU\(s\):" || true
cat /sys/kernel/mm/transparent_hugepage/enabled || true
echo "GLIBC_TUNABLES=${GLIBC_TUNABLES:-<unset>}"
cmake --version | head -1
g++ --version | head -1
gs --version || true
python3 --version

echo "=== 1. Unpack sources ==="
tar -xzf "$ROOT/w-d10-main.tar.gz" -C "$W/src-main"
tar -xzf "$ROOT/w-d10-fix.tar.gz" -C "$W/src-fix"
tar -xzf "$ROOT/w-d10-main.tar.gz" -C "$W/src-main-helper"
cp "$W/src-fix/tests/test_runner_numerics.cpp" "$W/src-main-helper/tests/test_runner_numerics.cpp"
echo "71ab841e69869b615555bb02f8f393db59c22d73" > "$W/src-main/SOURCE_COMMIT"
echo "97fb9fda5902f4bd5c2aab7c40ae4064637b5125" > "$W/src-fix/SOURCE_COMMIT"

echo "=== 2. Build Release CPU binaries inside allocation ==="
for arm in main fix main-helper; do
  taskset -c 0-15 cmake -S "$W/src-$arm" -B "$W/build-$arm" \
    -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON \
    > "$OUT/configure-$arm.log" 2>&1
  taskset -c 0-15 cmake --build "$W/build-$arm" -j 16 \
    > "$OUT/build-$arm.log" 2>&1
  grep -h -- "-O3" "$W/build-$arm/CMakeFiles/motioncorr.dir/flags.make" | head -1 | tee "$OUT/flags-$arm.txt"
done
sha256sum "$W/build-main/motioncorr" "$W/build-fix/motioncorr" "$W/build-main-helper/runner_numerics" "$W/build-fix/runner_numerics" | tee "$OUT/binaries.sha256"

echo "=== 3. Stage EER inputs node-local & warm page cache ==="
CORPUS=/work4/scd/scarf1415/mc-corpus-formats/data
mkdir -p "$W/data-12963/Movies" "$W/data-f3/Movies" "$W/data-f4/Movies"
cp -L "$CORPUS/EMPIAR-12963/data/EMPIAR-Deposition/RawMicrographs/Images-Disc1/GridSquare_4650264/Data/FoilHole_4674725_Data_4659374_4659376_20230406_014501_EER.eer" "$W/data-12963/Movies/movie1.eer"
cp -L "$CORPUS/EMPIAR-12963/data/EMPIAR-Deposition/GainReference/20230326_221855_EER_GainReference.gain" "$W/data-12963/gain.gain"
cp -L "$CORPUS/EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-39-45.801_eer_data_4096x4096.eer" "$W/data-f3/Movies/movie1.eer"
cp -L "$CORPUS/EMPIAR-10474/data/EER_raw_movies_Falcon4_47K_magnification/FoilHole_10919949_Data_10919593_10919595_20200711_001116_Fractions.mrc.eer" "$W/data-f4/Movies/movie1.eer"

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

cat "$W/data-12963/Movies/movie1.eer" "$W/data-12963/gain.gain" "$W/data-f3/Movies/movie1.eer" "$W/data-f4/Movies/movie1.eer" > /dev/null
sha256sum "$W/data-12963/Movies/movie1.eer" "$W/data-12963/gain.gain" "$W/data-f3/Movies/movie1.eer" "$W/data-f4/Movies/movie1.eer" | tee "$OUT/inputs.sha256"

echo "=== 4. Host EER decode-focused paired timing (AB/BA + AA null, 8 pairs) ==="
python3 - <<PY > "$OUT/decode_timing.json"
import json, subprocess, sys, time
sys.path.insert(0, "$W/src-fix/tools/profiling")
from lib import stats

main_h = "$W/build-main-helper/runner_numerics"
fix_h = "$W/build-fix/runner_numerics"
families = [
    ("e12963", "$W/data-12963/Movies/movie1.eer", "49"),
    ("e10474f3", "$W/data-f3/Movies/movie1.eer", "40"),
    ("e10474f4", "$W/data-f4/Movies/movie1.eer", "40"),
]

def run_once(helper, movie, grp):
    t0 = time.perf_counter()
    p = subprocess.run(["taskset", "-c", "0-7", helper, "count_eer", movie, "1", grp, "8"],
                       capture_output=True, text=True, check=True)
    dt = time.perf_counter() - t0
    elec = int(p.stdout.strip().split()[-1])
    return dt, elec

out = {}
for name, movie, grp in families:
    # Warmup
    _, e_m = run_once(main_h, movie, grp)
    _, e_f = run_once(fix_h, movie, grp)
    assert e_m == e_f, (name, e_m, e_f)
    ab_pairs = []
    for i in range(8):
        if i % 2 == 0:
            tm, em = run_once(main_h, movie, grp)
            tf, ef = run_once(fix_h, movie, grp)
        else:
            tf, ef = run_once(fix_h, movie, grp)
            tm, em = run_once(main_h, movie, grp)
        assert em == ef == e_m
        ab_pairs.append({"pair": i + 1, "order": "AB" if i % 2 == 0 else "BA", "main_s": tm, "fix_s": tf, "diff_s": tf - tm})
    aa_pairs = []
    for i in range(6):
        t1, e1 = run_once(main_h, movie, grp)
        t2, e2 = run_once(main_h, movie, grp)
        assert e1 == e2 == e_m
        aa_pairs.append({"pair": i + 1, "a1_s": t1, "a2_s": t2, "diff_s": t2 - t1})
    diffs = [p["diff_s"] for p in ab_pairs]
    null_diffs = [p["diff_s"] for p in aa_pairs]
    main_t = [p["main_s"] for p in ab_pairs]
    fix_t = [p["fix_s"] for p in ab_pairs]
    med_diff = stats.median(diffs)
    ci_lo, ci_hi = stats.median_ci(diffs)[:2]
    med_main = stats.median(main_t)
    med_fix = stats.median(fix_t)
    null_med = stats.median(null_diffs)
    null_ci = stats.median_ci(null_diffs)[:2]
    null_max = max(abs(x) for x in null_diffs)
    out[name] = {
        "electrons": e_m,
        "main_median_s": med_main,
        "main_iqr_s": stats.iqr(main_t),
        "fix_median_s": med_fix,
        "fix_iqr_s": stats.iqr(fix_t),
        "median_diff_s": med_diff,
        "pct_diff": 100.0 * med_diff / med_main,
        "ci95_s": [ci_lo, ci_hi],
        "pct_ci95": [100.0 * ci_lo / med_main, 100.0 * ci_hi / med_main],
        "null_median_s": null_med,
        "null_ci95_s": list(null_ci),
        "null_max_abs_s": null_max,
        "ab_pairs": ab_pairs,
        "aa_pairs": aa_pairs,
    }
print(json.dumps(out, indent=2))
PY
cat "$OUT/decode_timing.json"

echo "=== 5. Whole-job CPU paired timing: e12963 (6 AB/BA pairs + 6 AA null pairs) ==="
MC_12963=(--use_own --dose_weighting --dose_per_frame 1.282051282051282 --patch_x 5 --patch_y 5
          --bfactor 150 --gainref gain.gain --eer_grouping 49 --eer_upsampling 1
          --expected_frames 39 --seed 1 --skip_report_pdf --j 8)
python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
  main="$W/build-main/motioncorr" fix="$W/build-fix/motioncorr" \
  --source main="$W/src-main" --source fix="$W/src-fix" \
  --commit main=71ab841e69869b615555bb02f8f393db59c22d73 \
  --commit fix=97fb9fda5902f4bd5c2aab7c40ae4064637b5125 \
  --data "$W/data-12963" --star movies.star --work "$OUT/e12963_ab" \
  --cpus 0-7 --runner-cpus 16-19 --warmup 1 --pairs 6 --no-lock \
  -- "${MC_12963[@]}"

python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
  main="$W/build-main/motioncorr" main_null="$W/build-main/motioncorr" \
  --source main="$W/src-main" --source main_null="$W/src-main" \
  --commit main=71ab841e69869b615555bb02f8f393db59c22d73 \
  --commit main_null=71ab841e69869b615555bb02f8f393db59c22d73 \
  --data "$W/data-12963" --star movies.star --work "$OUT/e12963_aa" \
  --cpus 0-7 --runner-cpus 16-19 --warmup 1 --pairs 6 --no-lock \
  -- "${MC_12963[@]}"

echo "=== 6. Whole-job CPU paired timing: e10474f3 (6 AB/BA pairs + 6 AA null pairs) ==="
MC_F3=(--use_own --dose_weighting --dose_per_frame 1.0 --patch_x 5 --patch_y 5
       --bfactor 150 --eer_grouping 40 --eer_upsampling 1
       --expected_frames 58 --seed 1 --skip_report_pdf --j 8)
python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
  main="$W/build-main/motioncorr" fix="$W/build-fix/motioncorr" \
  --source main="$W/src-main" --source fix="$W/src-fix" \
  --commit main=71ab841e69869b615555bb02f8f393db59c22d73 \
  --commit fix=97fb9fda5902f4bd5c2aab7c40ae4064637b5125 \
  --data "$W/data-f3" --star movies.star --work "$OUT/e10474f3_ab" \
  --cpus 0-7 --runner-cpus 16-19 --warmup 1 --pairs 6 --no-lock \
  -- "${MC_F3[@]}"

python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
  main="$W/build-main/motioncorr" main_null="$W/build-main/motioncorr" \
  --source main="$W/src-main" --source main_null="$W/src-main" \
  --commit main=71ab841e69869b615555bb02f8f393db59c22d73 \
  --commit main_null=71ab841e69869b615555bb02f8f393db59c22d73 \
  --data "$W/data-f3" --star movies.star --work "$OUT/e10474f3_aa" \
  --cpus 0-7 --runner-cpus 16-19 --warmup 1 --pairs 6 --no-lock \
  -- "${MC_F3[@]}"

cat "$OUT/e12963_ab/report.md"
cat "$OUT/e12963_aa/report.md"
cat "$OUT/e10474f3_ab/report.md"
cat "$OUT/e10474f3_aa/report.md"
rm -rf "$W"
echo "SCARF_CPU_TIMING_COMPLETE $(date -u +%FT%TZ)"
