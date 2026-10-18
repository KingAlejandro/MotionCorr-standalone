#!/bin/bash
# Definitive pre-declared host EER decode timing design (#221 / RC0 D10):
# - Venue: SCARF exclusive CPU node (-p scarf --exclusive)
# - Workloads: host EER decode (runner_numerics count_eer, upsampling 1, 16 threads on CPUs 0-15)
#   on EMPIAR-12963 (grouping 49), EMPIAR-10474 Falcon 3 (grouping 40), EMPIAR-10474 Falcon 4 (grouping 40)
# - Design: 1 warmup per arm, N = 32 balanced pairs (16 AB + 16 BA interleaved), 12 AA null pairs
# - Exclusion rule: none (all 32 balanced pairs retained; 3-robust-SD outliers reported via stats.paired)
#SBATCH -p scarf
#SBATCH --nodes=1
#SBATCH --cpus-per-task=64
#SBATCH --exclusive
#SBATCH -t 01:30:00
#SBATCH -J wd10-dec32
#SBATCH -o /work4/scd/scarf1415/W-D10/slurm-def-decode-%j.out

set -euo pipefail
unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES PYTHONOPTIMIZE
export OMP_NUM_THREADS=16
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

ROOT=/work4/scd/scarf1415/W-D10
OUT="$ROOT/def-decode-${SLURM_JOB_ID}"
W="/tmp/wd10-dec-${SLURM_JOB_ID}"
mkdir -p "$OUT" "$W/src-main-helper" "$W/src-fix"

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

tar -xzf "$ROOT/w-d10-main.tar.gz" -C "$W/src-main-helper"
tar -xzf "$ROOT/w-d10-fix.tar.gz" -C "$W/src-fix"
cp "$W/src-fix/tests/test_runner_numerics.cpp" "$W/src-main-helper/tests/test_runner_numerics.cpp"

for arm in main-helper fix; do
  taskset -c 0-31 cmake -S "$W/src-$arm" -B "$W/build-$arm" \
    -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON \
    > "$OUT/configure-$arm.log" 2>&1
  taskset -c 0-31 cmake --build "$W/build-$arm" -j 32 --target runner_numerics \
    > "$OUT/build-$arm.log" 2>&1
done
sha256sum "$W/build-main-helper/runner_numerics" "$W/build-fix/runner_numerics" | tee "$OUT/binaries.sha256"

CORPUS=/work4/scd/scarf1415/mc-corpus-formats/data
mkdir -p "$W/data"
cp -L "$CORPUS/EMPIAR-12963/data/EMPIAR-Deposition/RawMicrographs/Images-Disc1/GridSquare_4650264/Data/FoilHole_4674725_Data_4659374_4659376_20230406_014501_EER.eer" "$W/data/e12963.eer"
cp -L "$CORPUS/EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-39-45.801_eer_data_4096x4096.eer" "$W/data/e10474f3.eer"
cp -L "$CORPUS/EMPIAR-10474/data/EER_raw_movies_Falcon4_47K_magnification/FoilHole_10919949_Data_10919593_10919595_20200711_001116_Fractions.mrc.eer" "$W/data/e10474f4.eer"
cat "$W/data/e12963.eer" "$W/data/e10474f3.eer" "$W/data/e10474f4.eer" > /dev/null
sha256sum "$W/data/"*.eer | tee "$OUT/inputs.sha256"

python3 -u - <<PY | tee "$OUT/decode_32pairs_summary.txt"
import json, subprocess, sys, time
sys.path.insert(0, "$W/src-fix/tools/profiling")
from lib import stats

main_h = "$W/build-main-helper/runner_numerics"
fix_h = "$W/build-fix/runner_numerics"
families = [
    ("e12963", "$W/data/e12963.eer", "49"),
    ("e10474f3", "$W/data/e10474f3.eer", "40"),
    ("e10474f4", "$W/data/e10474f4.eer", "40"),
]

def run_once(helper, movie, grp):
    t0 = time.perf_counter()
    p = subprocess.run(["taskset", "-c", "0-15", helper, "count_eer", movie, "1", grp, "16"],
                       capture_output=True, text=True, check=True)
    dt = time.perf_counter() - t0
    elec = int(p.stdout.strip().split()[-1])
    return dt, elec

out = {}
for name, movie, grp in families:
    _, e_m = run_once(main_h, movie, grp)
    _, e_f = run_once(fix_h, movie, grp)
    assert e_m == e_f
    ab_pairs = []
    for i in range(32):
        if i % 2 == 0:
            tm, em = run_once(main_h, movie, grp)
            tf, ef = run_once(fix_h, movie, grp)
            order = "AB"
        else:
            tf, ef = run_once(fix_h, movie, grp)
            tm, em = run_once(main_h, movie, grp)
            order = "BA"
        assert em == ef == e_m
        ab_pairs.append({"pair": i + 1, "order": order, "a": tm, "b": tf, "diff_s": tf - tm})
        if (i + 1) % 8 == 0:
            print(f"{name}: completed {i+1}/32 AB/BA pairs", flush=True)
    aa_pairs = []
    for i in range(12):
        t1, e1 = run_once(main_h, movie, grp)
        t2, e2 = run_once(main_h, movie, grp)
        assert e1 == e2 == e_m
        aa_pairs.append({"pair": i + 1, "order": "AA", "a": t1, "b": t2, "diff_s": t2 - t1})
    diffs = [p["diff_s"] for p in ab_pairs]
    null_diffs = [p["diff_s"] for p in aa_pairs]
    main_t = [p["a"] for p in ab_pairs]
    fix_t = [p["b"] for p in ab_pairs]
    med_main = stats.median(main_t)
    med_fix = stats.median(fix_t)
    med_diff = stats.median(diffs)
    ci_lo, ci_hi, ci_conf = stats.median_ci(diffs)
    null_ci_lo, null_ci_hi, _ = stats.median_ci(null_diffs)
    out[name] = {
        "electrons": e_m,
        "n_ab_pairs": 32,
        "n_ab": 16,
        "n_ba": 16,
        "n_aa_null_pairs": 12,
        "main_median_s": med_main,
        "main_iqr_s": stats.iqr(main_t),
        "main_robust_sd_s": stats.robust_sd(main_t),
        "fix_median_s": med_fix,
        "fix_iqr_s": stats.iqr(fix_t),
        "fix_robust_sd_s": stats.robust_sd(fix_t),
        "median_diff_s": med_diff,
        "pct_diff": 100.0 * med_diff / med_main,
        "ci95_s": [ci_lo, ci_hi],
        "ci_achieved": ci_conf,
        "pct_ci95": [100.0 * ci_lo / med_main, 100.0 * ci_hi / med_main],
        "upper_ci_le_0p5pct": (100.0 * ci_hi / med_main) <= 0.5,
        "null_median_s": stats.median(null_diffs),
        "null_ci95_s": [null_ci_lo, null_ci_hi],
        "null_max_abs_s": max(abs(x) for x in null_diffs),
        "paired_summary": stats.paired(ab_pairs),
        "null_summary": stats.paired(aa_pairs),
        "ab_pairs": ab_pairs,
        "aa_pairs": aa_pairs,
    }
    with open("$OUT/decode_32pairs.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"DONE {name}: main={med_main:.4f}s fix={med_fix:.4f}s diff={med_diff:+.4f}s ({100*med_diff/med_main:+.2f}%) CI=[{ci_lo:+.4f}, {ci_hi:+.4f}]s ([{100*ci_lo/med_main:+.2f}%, {100*ci_hi/med_main:+.2f}%]) null_max={max(abs(x) for x in null_diffs):.4f}s", flush=True)
PY
rm -rf "$W"
echo "DEF_DECODE_COMPLETE $(date -u +%FT%TZ)"
