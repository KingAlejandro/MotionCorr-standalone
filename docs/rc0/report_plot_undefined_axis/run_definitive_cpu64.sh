#!/bin/bash
# Pre-specified Definitive Paired Whole-Job CPU Comparison for Issue #229 (D13 / D14)
#
# Fixed Design (declared before execution from the separate 4-pair cpu64 pilot):
#   - Venue & Node:     cpu64 (small-refmac-machine, 2x AMD EPYC 7763 64-Core, THP madvise)
#   - Mutex Lock:       /tmp/motioncorr-cpu64-bench.lock held via flock for the entire window
#   - CPU Affinity:     Payload pinned to CPUs 48-55 (single 8-core CCD on NUMA node 1, --j 8,
#                       OMP_NUM_THREADS=8); mcprof sampler pinned to CPUs 56-59
#   - Environment:      GLIBC_TUNABLES unset, OMP_PROC_BIND/OMP_PLACES unset, OPENBLAS_NUM_THREADS=1
#   - Binaries:         Matched Release (-O3 -DNDEBUG -std=gnu++17 -fopenmp, -DCUDA=OFF):
#                         main (1afa03b57afbae42138ee30c3545b57b5a74c321):
#                           sha256 307a030b03785201342a57c4d8adae14120d87676fa6bec7e62f8959d5b03a35
#                         fix  (b82d25f4dda6bca746e4206fed1272851cc6a5ce):
#                           sha256 68dc7ac11049bb15be3caa90af10adb6c7bb7e44b752d797080b9ca1a79d96f9
#   - Workload:         2-movie tutorial subset (movies2.star: 20170629_00021_frameImage.tiff,
#                       20170629_00022_frameImage.tiff + gain.mrc, staged in /dev/shm tmpfs),
#                       selected from the pilot (0.2371% vs 1.6576% rel_sigma/sqrt(min)).
#   - Payload Options:  --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
#                       --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8
#                       (report generation ON: no --skip_report_pdf; writes logfile.pdf + EPS)
#   - Sample Size & Order:
#       1. AB/BA Comparison (main vs fix):
#          - 1 unrecorded warmup per arm (r00: main, fix)
#          - N = 32 retained pairs, deterministic alternating schedule:
#            odd rounds (r01, r03, ..., r31) = AB (main then fix), 16 pairs;
#            even rounds (r02, r04, ..., r32) = BA (fix then main), 16 pairs.
#            Exact balance: 16 AB / 16 BA.
#       2. AA Null Comparison (main vs main_null, identical binary):
#          - 1 unrecorded warmup per arm (r00: main, main_null)
#          - N_null = 12 retained pairs, deterministic alternating schedule:
#            odd rounds (r01, r03, ..., r11) = AB, 6 pairs;
#            even rounds (r02, r04, ..., r12) = BA, 6 pairs.
#            Exact balance: 6 AB / 6 BA.
#   - Exclusion Rule:
#       Before each round mcprof waits up to 300 s for lane 48-55 foreign CPU <= 0.25 cores.
#       A pair is discarded only if either run in the pair has a non-zero exit (rc != 0),
#       fewer than 2 MRC products, an unverified executable path, a payload affinity mismatch
#       (!= [48..55]), or recorded foreign CPU > 0.25 cores on lane 48-55. Any discarded pair
#       removes both arms of that round.
#   - Acceptance Criterion (Maintainer Decision D14):
#       - Pass:       no resolved slowdown, AND upper >=95% CI bound of median(fix - main)
#                     <= +0.5% of median(main) whole-job wall time.
#       - Unresolved: no resolved slowdown, but upper >=95% CI bound > +0.5% of median(main).
#       - Fail:       resolved slowdown.

set -euo pipefail

unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES PYTHONOPTIMIZE
export PATH=/home/ubuntu/.mc-venv/bin:$PATH
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=1

W=/home/ubuntu/mc-w-d13
SHM=/dev/shm/mc-w-d13-definitive
OUT=$W/definitive
rm -rf "$SHM" "$OUT"
mkdir -p "$SHM/data/Movies" "$OUT"

exec > >(tee "$OUT/definitive.log") 2>&1

echo "=== 0. Definitive Run Provenance (cpu64) ==="
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

  echo "=== 1. Definitive AB/BA Comparison: main vs fix (N=32 pairs: 16 AB / 16 BA, warmup 1, CPUs 48-55) ==="
  python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
    main="$W/build-main/motioncorr" fix="$W/build-fix/motioncorr" \
    --source main="$W/src-main" --source fix="$W/src-fix" \
    --commit main=1afa03b57afbae42138ee30c3545b57b5a74c321 \
    --commit fix=b82d25f4dda6bca746e4206fed1272851cc6a5ce \
    --data "$SHM/data" --star movies2.star --work "$SHM/ab_32" \
    --cpus 48-55 --runner-cpus 56-59 --no-lock \
    --lane-wait 300 --warmup 1 --pairs 32 --max-rounds 32 \
    -- "${MC_ARGS[@]}"

  echo "=== 2. Definitive AA Null Comparison: main vs main_null (N_null=12 pairs: 6 AB / 6 BA, warmup 1, CPUs 48-55) ==="
  python3 "$W/src-fix/tools/profiling/mcprof.py" compare \
    main="$W/build-main/motioncorr" main_null="$W/build-main/motioncorr" \
    --source main="$W/src-main" --source main_null="$W/src-main" \
    --commit main=1afa03b57afbae42138ee30c3545b57b5a74c321 \
    --commit main_null=1afa03b57afbae42138ee30c3545b57b5a74c321 \
    --data "$SHM/data" --star movies2.star --work "$SHM/aa_12" \
    --cpus 48-55 --runner-cpus 56-59 --no-lock \
    --lane-wait 300 --warmup 1 --pairs 12 --max-rounds 12 \
    -- "${MC_ARGS[@]}"
)

cp -r "$SHM/ab_32" "$SHM/aa_12" "$OUT/"
rm -rf "$SHM"

echo "=== 3. Definitive D14 Evaluation ==="
python3 - "$OUT/ab_32" "$OUT/aa_12" "$OUT/definitive_summary.json" << 'PY'
import json, pathlib, sys

ab_dir = pathlib.Path(sys.argv[1])
aa_dir = pathlib.Path(sys.argv[2])
out_json = pathlib.Path(sys.argv[3])

ab_cmp = json.loads((ab_dir / "compare.json").read_text())["runs"]
aa_cmp = json.loads((aa_dir / "compare.json").read_text())["runs"]

ab_pair = ab_cmp["comparisons"]["fix"]
aa_pair = aa_cmp["comparisons"]["main_null"]

ab_main = ab_cmp["summary"]["main"]
ab_fix = ab_cmp["summary"]["fix"]
aa_main = aa_cmp["summary"]["main"]
aa_null = aa_cmp["summary"]["main_null"]

t_main_med = ab_main["wall_median_s"]
ci_lo = ab_pair["ci"]["low_s"]
ci_hi = ab_pair["ci"]["high_s"]
ci_cov = ab_pair["ci"]["confidence"]
d_med = ab_pair["median_diff_s"]
d_med_pct = (d_med / t_main_med) * 100.0
ci_lo_pct = (ci_lo / t_main_med) * 100.0
ci_hi_pct = (ci_hi / t_main_med) * 100.0
d14_threshold_s = 0.005 * t_main_med

null_diffs = aa_pair["diffs_s"]
null_max_abs_s = max(abs(x) for x in null_diffs)
null_max_abs_pct = (null_max_abs_s / aa_main["wall_median_s"]) * 100.0

if ab_pair.get("verdict") == "resolved slower":
    d14_verdict = "Fail"
elif ci_hi_pct <= 0.5:
    d14_verdict = "Pass"
else:
    d14_verdict = "Unresolved"

summary = {
    "d14_margin_pct": 0.5,
    "d14_threshold_s": round(d14_threshold_s, 6),
    "d14_verdict": d14_verdict,
    "ab_32": {
        "n_pairs": ab_pair["n_pairs"],
        "kept_orders": ab_cmp["discard_audit"]["kept_orders"],
        "discarded": ab_cmp["discard_audit"]["discarded"],
        "main_wall_s": ab_main,
        "fix_wall_s": ab_fix,
        "median_diff_s": round(d_med, 6),
        "median_diff_pct": round(d_med_pct, 4),
        "ci_low_s": round(ci_lo, 6),
        "ci_high_s": round(ci_hi, 6),
        "ci_low_pct": round(ci_lo_pct, 4),
        "ci_high_pct": round(ci_hi_pct, 4),
        "ci_confidence": round(ci_cov, 6),
        "q1_diff_s": round(ab_pair["q1_diff_s"], 6),
        "q3_diff_s": round(ab_pair["q3_diff_s"], 6),
        "noise_s": round(ab_pair["noise_s"], 6),
        "noise_pct": round((ab_pair["noise_s"] / t_main_med) * 100.0, 4),
        "sign_test": ab_pair["sign_test"],
        "mcprof_verdict": ab_pair["verdict"],
    },
    "aa_12": {
        "n_pairs": aa_pair["n_pairs"],
        "kept_orders": aa_cmp["discard_audit"]["kept_orders"],
        "discarded": aa_cmp["discard_audit"]["discarded"],
        "main_wall_s": aa_main,
        "main_null_wall_s": aa_null,
        "median_diff_s": round(aa_pair["median_diff_s"], 6),
        "median_diff_pct": round((aa_pair["median_diff_s"] / aa_main["wall_median_s"]) * 100.0, 4),
        "ci_low_s": round(aa_pair["ci"]["low_s"], 6),
        "ci_high_s": round(aa_pair["ci"]["high_s"], 6),
        "ci_low_pct": round((aa_pair["ci"]["low_s"] / aa_main["wall_median_s"]) * 100.0, 4),
        "ci_high_pct": round((aa_pair["ci"]["high_s"] / aa_main["wall_median_s"]) * 100.0, 4),
        "ci_confidence": round(aa_pair["ci"]["confidence"], 6),
        "noise_s": round(aa_pair["noise_s"], 6),
        "null_max_abs_s": round(null_max_abs_s, 6),
        "null_max_abs_pct": round(null_max_abs_pct, 4),
        "sign_test": aa_pair["sign_test"],
        "mcprof_verdict": aa_pair["verdict"],
    },
}
print(json.dumps(summary, indent=2))
out_json.write_text(json.dumps(summary, indent=2) + "\n")
PY

cat "$OUT/ab_32/report.md"
echo "---"
cat "$OUT/aa_12/report.md"
echo "DEFINITIVE_CPU64_COMPLETE $(date -u +%FT%TZ)"
