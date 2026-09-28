#!/bin/bash
# Issue #74 - Optional CUDA profiling overhead.
#
# One dedicated, exclusive, single-node GPU allocation. Everything below runs on
# that one node so that source, compiler, toolkit, device, build options, input
# staging and filesystem cache are common to every arm of every comparison.
#
# Arms:
#   base     baseline binary built from 1d7e13f (pre-change), unchanged behaviour
#   cand-on  candidate binary, detailed event profiling ENABLED  (the default)
#   cand-off candidate binary, detailed event profiling DISABLED (RELION_CUDA_DETAILED_PROFILE=0)
#
# cand-on and cand-off are the SAME BYTES. The switch is a runtime environment
# variable precisely so that codegen cannot be a confounder in the A/B.
#
# The job never exits early on a failed gate: a failure is recorded in
# summary.txt and the remaining evidence is still collected. Read summary.txt.

#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 04:00:00
#SBATCH -J mc-i74
#SBATCH -o /home/vol05/scarf1415/mc-issue74-run/slurm-%j.out

set -uo pipefail

export CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export TMPDIR=/tmp

BUNDLE=/home/vol05/scarf1415/mc-issue74.bundle
CAND=/home/vol05/scarf1415/mc-issue74
BASE=/home/vol05/scarf1415/mc-issue74-base
RUN=/home/vol05/scarf1415/mc-issue74-run
E="$RUN/ev-${SLURM_JOB_ID}"
W="/tmp/i74-${SLURM_JOB_ID}"
# The candidate clone tracks the branch tip, which also carries documentation
# commits. What must be pinned is the code that gets compiled, so the job
# asserts that everything it builds is identical to the reviewed code commit
# and records the actual tip separately.
CODE_SHA=e0bc6c3257dd9a046a7c85bb40b16b73e4d57302
BASE_SHA=1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26
BUILT_PATHS=(src CMakeLists.txt tests)
REF=/home/vol05/scarf1415/mc-stabilize-20260926/evidence/baseline
COMPARE24=/home/vol05/scarf1415/compare24.py
SRC_MOVIES=/home/vol05/scarf1415/i53-scarf/relion30_tutorial/Movies
SRC_STAR=/home/vol05/scarf1415/i53-scarf/runroot/movies.star

MC_ARGS=(--j 8 --use_own --dose_weighting --dose_per_frame 1.277
         --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1)

mkdir -p "$E" "$W"
exec > >(tee "$E/job.log") 2>&1

SUMMARY="$E/summary.txt"
: > "$SUMMARY"
record() { # record <verdict> <label>
    printf '%-8s %s\n' "$1" "$2" | tee -a "$SUMMARY"
}
gate() { # gate <label> <cmd...>
    local label="$1"; shift
    if "$@"; then record PASS "$label"; else record FAIL "$label"; fi
}

echo "=============== 0. provenance ==============="
date -Is
hostname
scontrol show job "$SLURM_JOB_ID" | grep -E 'NodeList|NumCPUs|TRES|Gres' || true
squeue -u "$USER" -o '%.10i %.9P %.10j %.2t %.6M %R'
grep Cpus_allowed_list /proc/self/status
uptime
nvidia-smi
nvcc --version
cmake --version | head -1
gcc --version | head -1
df -h /tmp

echo "=============== 1. source trees ==============="
# The candidate clone already exists (transferred as a bundle: SCARF has no
# outbound git network). The baseline clone is made from the same bundle, so
# both arms come from one byte-identical object store.
if [ ! -d "$BASE/.git" ]; then
    git clone --no-checkout "$BUNDLE" "$BASE"
fi
git -C "$BASE" checkout --detach "$BASE_SHA"
git -C "$CAND" status --porcelain
git -C "$BASE" status --porcelain

GOT_CAND=$(git -C "$CAND" rev-parse HEAD)
GOT_BASE=$(git -C "$BASE" rev-parse HEAD)
echo "candidate tip  = $GOT_CAND"
echo "baseline  HEAD = $GOT_BASE (want $BASE_SHA)"
CODE_DRIFT=$(git -C "$CAND" diff --name-only "$CODE_SHA" HEAD -- "${BUILT_PATHS[@]}")
echo "compiled-path drift vs $CODE_SHA: ${CODE_DRIFT:-<none>}"
if [ "$GOT_BASE" = "$BASE_SHA" ] && [ -z "$CODE_DRIFT" ]; then
    record PASS "baseline at $BASE_SHA; every compiled path identical to $CODE_SHA (tip $GOT_CAND)"
else
    record FAIL "source trees at the intended commits"
    echo "refusing to continue: wrong commits or compiled-path drift"; exit 1
fi

# The two arms must differ in exactly the files this issue owns.
git -C "$CAND" diff --stat "$BASE_SHA" "$CODE_SHA" | tee "$E/candidate-vs-baseline.diffstat"
git -C "$CAND" diff "$BASE_SHA" "$CODE_SHA" > "$E/candidate-vs-baseline.diff"

sha256sum "$CAND"/src/acc/cuda/*.cu "$CAND"/src/acc/cuda/*.h \
          "$BASE"/src/acc/cuda/*.cu "$BASE"/src/acc/cuda/*.h > "$E/sources.sha256"

echo "=============== 2. builds (identical options) ==============="
CMAKE_OPTS=(-DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80
            -DTIMING=ON -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc"
            -DCUDAToolkit_ROOT="$CUDA_HOME")
printf '%s\n' "${CMAKE_OPTS[@]}" > "$E/cmake-options.txt"

for T in "$BASE" "$CAND"; do
    N=$(basename "$T")
    rm -rf "$T/build-cuda"
    cmake -S "$T" -B "$T/build-cuda" "${CMAKE_OPTS[@]}" > "$E/configure-$N.log" 2>&1 \
        || { record FAIL "configure $N"; tail -40 "$E/configure-$N.log"; exit 1; }
    cmake --build "$T/build-cuda" --parallel 8 > "$E/build-$N.log" 2>&1 \
        || { record FAIL "build $N"; tail -60 "$E/build-$N.log"; exit 1; }
    record PASS "build $N"
done
sha256sum "$BASE/build-cuda/motioncorr" "$CAND/build-cuda/motioncorr" | tee "$E/binaries.sha256"

BASE_BIN="$BASE/build-cuda/motioncorr"
CAND_BIN="$CAND/build-cuda/motioncorr"

echo "=============== 3. unit / wrapper controls ==============="
gate "ctest CudaProfilePolicyDefault (candidate)" \
    ctest --test-dir "$CAND/build-cuda" -R CudaProfilePolicyDefault --output-on-failure
gate "ctest CudaWrapperUploadFailure (candidate)" \
    ctest --test-dir "$CAND/build-cuda" -R CudaWrapperUploadFailure --output-on-failure
gate "ctest CudaWrapperUploadFailure (baseline)" \
    ctest --test-dir "$BASE/build-cuda" -R CudaWrapperUploadFailure --output-on-failure
# The aux comparator is itself a gate, so it needs its own test in the same run;
# an instrument that silently accepts everything would make section 6 look good.
gate "aux comparator self-test (incl. old-source negative controls)" \
    python3 "$CAND/docs/issue74/test_compare_aux_outputs.py"
# The policy test does not exist on the baseline tree; that is expected, not a failure.
ctest --test-dir "$BASE/build-cuda" -N | tee "$E/ctest-baseline-list.txt" | tail -5

echo "=============== 4. stage inputs node-local ==============="
mkdir -p "$W/in" "$W/out" "$W/t"
cp -L "$SRC_STAR" "$W/in/movies.star"
cp -rL "$SRC_MOVIES" "$W/in/Movies"
du -sh "$W/in"
( cd "$W/in" && find . -type f | sort | xargs sha256sum ) > "$E/inputs.sha256"
sha256sum "$E/inputs.sha256"
wc -l "$E/inputs.sha256"

echo "=============== 5. correctness runs (all 24 tutorial movies) ==============="
run_all24() { # run_all24 <tag> <binary> <profile-env-or-unset>
    # Deliberately separate statements: under `set -u`, a name declared in the
    # same `local` is not yet usable by a later assignment in that declaration.
    local tag="$1" bin="$2" prof="$3"
    local out="$W/out/$tag"
    mkdir -p "$out"
    echo "--- run_all24 $tag bin=$bin RELION_CUDA_DETAILED_PROFILE=${prof:-<unset>}"
    ( cd "$W/in"
      if [ -n "$prof" ]; then export RELION_CUDA_DETAILED_PROFILE="$prof"
      else unset RELION_CUDA_DETAILED_PROFILE; fi
      env | grep -E '^RELION_CUDA_DETAILED_PROFILE=' || echo "RELION_CUDA_DETAILED_PROFILE unset"
      /usr/bin/time -v "$bin" --i movies.star --o "$out/" --gpu 0 "${MC_ARGS[@]}" \
          > "$E/run-$tag.stdout" 2> "$E/run-$tag.time" )
    echo "exit=$?"
    grep -c 'Using CUDA acceleration on GPU device 0' "$E/run-$tag.stdout" \
        > "$E/run-$tag.startup_markers"
    grep -l '\[CUDA Global Alignment\] completed; converged=' "$out"/Movies/*.log \
        | wc -l > "$E/run-$tag.completion_markers"
    echo "$tag startup markers: $(cat "$E/run-$tag.startup_markers")"
    echo "$tag completion markers: $(cat "$E/run-$tag.completion_markers")"
}

run_all24 base     "$BASE_BIN" ""
run_all24 cand-on  "$CAND_BIN" ""
run_all24 cand-off "$CAND_BIN" "0"

# Execution witness: the candidate with detailed profiling OFF must still prove
# it actually started and completed on the GPU. 24 movies -> 24 completion markers.
for tag in base cand-on cand-off; do
    S=$(cat "$E/run-$tag.startup_markers"); C=$(cat "$E/run-$tag.completion_markers")
    if [ "$S" -ge 1 ] && [ "$C" -eq 24 ]; then
        record PASS "CUDA execution witness $tag (startup=$S completion=$C/24)"
    else
        record FAIL "CUDA execution witness $tag (startup=$S completion=$C/24)"
    fi
done

echo "=============== 6. exactness gates ==============="
# Gate C: pixels, MRC headers, per-movie STAR trajectories. Fails closed.
exact() { # exact <refdir> <testdir> <outtag>
    python3 "$COMPARE24" --ref "$1" --test "$2" \
        --tool "$CAND/tools/compare_motioncorr.py" --out "$E/exact-$3" \
        > "$E/exact-$3.log" 2>&1
    local rc=$?
    tail -3 "$E/exact-$3.log"
    return $rc
}
gate "exact24 cand-on vs merged-reference"  exact "$REF"           "$W/out/cand-on"  "candon-vs-ref"
gate "exact24 cand-off vs merged-reference" exact "$REF"           "$W/out/cand-off" "candoff-vs-ref"
gate "exact24 base vs merged-reference"     exact "$REF"           "$W/out/base"     "base-vs-ref"
gate "exact24 cand-off vs cand-on (same node, same binary)" \
                                            exact "$W/out/cand-on" "$W/out/cand-off" "candoff-vs-candon"
gate "exact24 cand-on vs base (same node)"  exact "$W/out/base"    "$W/out/cand-on"  "candon-vs-base"

# Everything the exactness gate does not read: corrected_micrographs.star,
# the _shifts.eps trajectories, and every non-timing line of all 24 logs.
AUX="$CAND/docs/issue74/compare_aux_outputs.py"
gate "aux outputs cand-off vs cand-on" \
    python3 "$AUX" --ref "$W/out/cand-on" --test "$W/out/cand-off" \
        --report "$E/aux-candoff-vs-candon.txt"
gate "aux outputs cand-on vs base (labels allowed to change)" \
    python3 "$AUX" --ref "$W/out/base" --test "$W/out/cand-on" --allow-label-changes \
        --report "$E/aux-candon-vs-base.txt"

# The intended difference must actually be present, or the OFF arm did nothing.
# Both reporting sites (alignment and dose-weighted reconstruction) print this
# line with their own indentation, so compare the reported value, not the line.
det_values() { grep -h 'Detailed event profiling:' "$1"/Movies/*.log | awk '{print $NF}' | sort -u | paste -sd,; }
det_sites()  { grep -hc 'Detailed event profiling:' "$1"/Movies/20170629_00021_frameImage.log; }
ON_DET=$(det_values "$W/out/cand-on")
OFF_DET=$(det_values "$W/out/cand-off")
echo "cand-on  values: [$ON_DET], lines in one movie log: $(det_sites "$W/out/cand-on")"
echo "cand-off values: [$OFF_DET], lines in one movie log: $(det_sites "$W/out/cand-off")"
# 26 alignment profiles (1 global + 25 patches) + 1 DW reconstruction = 27 per movie.
if [ "$ON_DET" = "on" ] && [ "$OFF_DET" = "off" ] && \
   [ "$(det_sites "$W/out/cand-on")" -eq 27 ] && [ "$(det_sites "$W/out/cand-off")" -eq 27 ]; then
    record PASS "the switch actually switched (uniform on/off at all 27 sites, all 24 logs)"
else
    record FAIL "the switch actually switched"
fi

echo "=============== 7. known-motion gates + CPU masquerade control ==============="
kmg() { # kmg <tag> <binary> <prof> <extra args...>
    local tag="$1" bin="$2" prof="$3"; shift 3
    ( if [ -n "$prof" ]; then export RELION_CUDA_DETAILED_PROFILE="$prof"
      else unset RELION_CUDA_DETAILED_PROFILE; fi
      cd "$CAND"
      python3 tools/run_known_motion_gates.py --binary "$bin" --include-heavy \
          --outdir "$E/kmg-$tag" --json "$E/kmg-$tag.json" "$@" ) \
        > "$E/kmg-$tag.log" 2>&1
}
# Two different questions are deliberately kept apart here.
#
#   (a) BACKEND WITNESS - did this actually execute on CUDA? Judged only from
#       backend_evidence in the JSON, by check_backend_witness.py.
#   (b) ESTIMATOR ACCURACY - the aggregate gate verdict. Reported, never used to
#       answer (a). Historical CPU accuracy failures remain failures and are not
#       this issue's to hide or to fix, so grading the CPU masquerade control on
#       the aggregate exit status would be wrong in both directions.
WIT="$CAND/docs/issue74/check_backend_witness.py"

for arm in "cand-on:$CAND_BIN:" "cand-off:$CAND_BIN:0" "base:$BASE_BIN:"; do
    tag=${arm%%:*}; rest=${arm#*:}; bin=${rest%%:*}; prof=${rest#*:}
    kmg "$tag" "$bin" "$prof" --gpu 0
    rc=$?
    echo "known-motion aggregate exit for $tag: $rc (accuracy + gates; NOT the backend verdict)"
    record INFO "known-motion aggregate (accuracy) $tag: exit=$rc"
    gate "CUDA execution witness, known-motion gates, $tag" \
        python3 "$WIT" --json "$E/kmg-$tag.json" --expect cuda \
            --report "$E/witness-$tag.txt"
done

# No --gpu: backend_evidence() must REJECT any run that shows a CUDA marker.
# A pass here is what makes the marker a witness rather than a printed string.
kmg cpu-control "$CAND_BIN" "0"
echo "known-motion aggregate exit for cpu-control: $? (accuracy; NOT the backend verdict)"
gate "CPU masquerade rejection (no CUDA marker on a CPU run)" \
    python3 "$WIT" --json "$E/kmg-cpu-control.json" --expect cpu \
        --report "$E/witness-cpu-control.txt"

echo "=============== 8. paired interleaved timing (ABBA x3) ==============="
# One binary, two environments. Blocks are ABBA so that linear drift in node
# state cancels. Each run writes a fresh output directory and is hashed, so a
# timing run that silently produced different results cannot be mistaken for a
# clean one.
: > "$E/timing.tsv"
printf 'order\ttag\twall_s\tmax_rss_kb\tstar_digest\n' >> "$E/timing.tsv"
ORDER=0
timed_run() { # timed_run <tag> <binary> <prof>
    local tag="$1" bin="$2" prof="$3"
    ORDER=$((ORDER+1))
    local out="$W/t/${ORDER}-${tag}"
    mkdir -p "$out"
    ( cd "$W/in"
      if [ -n "$prof" ]; then export RELION_CUDA_DETAILED_PROFILE="$prof"
      else unset RELION_CUDA_DETAILED_PROFILE; fi
      /usr/bin/time -v "$bin" --i movies.star --o "$out/" --gpu 0 "${MC_ARGS[@]}" \
          > "$E/t-${ORDER}-${tag}.stdout" 2> "$E/t-${ORDER}-${tag}.time" )
    local wall rss dig
    wall=$(awk -F': ' '/Elapsed \(wall clock\)/{print $NF}' "$E/t-${ORDER}-${tag}.time")
    rss=$(awk -F': ' '/Maximum resident set size/{print $NF}' "$E/t-${ORDER}-${tag}.time")
    dig=$(cat "$out"/Movies/*.star | sha256sum | cut -c1-16)
    printf '%s\t%s\t%s\t%s\t%s\n' "$ORDER" "$tag" "$wall" "$rss" "$dig" >> "$E/timing.tsv"
    echo "run $ORDER $tag wall=$wall rss=$rss star_digest=$dig"
    # Keep only the first output tree per arm; the rest are hashed then dropped.
    if [ "$ORDER" -gt 2 ]; then rm -rf "$out"; fi
}

for block in 1 2 3; do
    timed_run cand-on  "$CAND_BIN" ""
    timed_run cand-off "$CAND_BIN" "0"
    timed_run cand-off "$CAND_BIN" "0"
    timed_run cand-on  "$CAND_BIN" ""
done
# Baseline binary at both ends, as a drift and cross-version check.
timed_run base "$BASE_BIN" ""
timed_run base "$BASE_BIN" ""

column -t "$E/timing.tsv" || cat "$E/timing.tsv"

# Every timing run of every arm must have produced the same trajectories.
NDIG=$(awk 'NR>1{print $5}' "$E/timing.tsv" | sort -u | wc -l)
if [ "$NDIG" -eq 1 ]; then
    record PASS "all timing runs produced identical per-movie STAR trajectories"
else
    record FAIL "timing runs disagreed on trajectories ($NDIG distinct digests)"
    awk 'NR>1{print $2, $5}' "$E/timing.tsv" | sort -u
fi

echo "=============== 9. GPU memory sampling, one pair ==============="
sample_pair() { # sample_pair <tag> <prof>
    local tag="$1" prof="$2"
    local out="$W/t/mem-$tag"
    mkdir -p "$out"
    nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu \
        --format=csv,noheader -l 1 > "$E/nvsmi-$tag.csv" &
    local pid=$!
    ( cd "$W/in"
      if [ -n "$prof" ]; then export RELION_CUDA_DETAILED_PROFILE="$prof"
      else unset RELION_CUDA_DETAILED_PROFILE; fi
      /usr/bin/time -v "$CAND_BIN" --i movies.star --o "$out/" --gpu 0 "${MC_ARGS[@]}" \
          > "$E/mem-$tag.stdout" 2> "$E/mem-$tag.time" )
    kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
    echo "$tag peak GPU MiB: $(awk -F', ' '{gsub(/ MiB/,"",$2); if($2+0>m)m=$2+0} END{print m}' "$E/nvsmi-$tag.csv")"
    echo "$tag max RSS kB:   $(awk -F': ' '/Maximum resident set size/{print $NF}' "$E/mem-$tag.time")"
    rm -rf "$out"
}
sample_pair on ""
sample_pair off "0"

echo "=============== 10. collect ==============="
cp "$E"/timing.tsv "$E"/summary.txt "$RUN/" 2>/dev/null || true
du -sh "$E"
echo
echo "================= SUMMARY ================="
cat "$SUMMARY"
echo "FAILures: $(grep -c '^FAIL' "$SUMMARY")"
date -Is
rm -rf "$W"
