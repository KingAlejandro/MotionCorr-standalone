#!/usr/bin/env bash
# PR110 combined correctness foundation -- native CUDA run on the shared 4-GPU VM.
#
# Device: GPU3 only, selected by UUID (ordinals never identify silicon).
#   #53 owns GPU0/1 + CPUs 96-111, #69 owns GPU2 + CPUs 112-119. This job takes
#   the previously unallocated GPU3 and CPUs 120-123 (node1), disjoint from both.
#   Alex explicitly requested a 4-GPU-VM run in addition to SCARF; this extends
#   the previously published collective envelope (24 CPUs / 3 devices) and is
#   recorded as such rather than done quietly.
# Lock: /tmp/motioncorr-gpu3-pr110.lock (own device lock; correctness, not timing,
#   so the benchmark mutex is deliberately not taken and no timing is claimed).
set -uo pipefail
trap '' PIPE
GPU3_UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
R=/home/alex/mc-pr110-gpu3
BUNDLE=/home/alex/mc-pr110.bundle
T=/home/alex/MotionCorr-standalone/relion30_tutorial
VENV=/home/alex/.mc-i96-venv
BASE=4c952b3f54479653512c4d208e09c9a8c02f3726
export PATH=/usr/local/cuda/bin:$PATH
export OMP_NUM_THREADS=4
rm -rf "$R"; mkdir -p "$R/logs"; LOG=$R/logs
exec > >(tee -a "$LOG/gpu3.log") 2>&1

echo "################ PRE-FLIGHT OCCUPANCY (abort on conflict) ################"
date -u +"UTC %Y-%m-%dT%H:%M:%SZ"; hostname
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv
BUSY=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$GPU3_UUID")
if [ "$BUSY" -ne 0 ]; then echo "ABORT: GPU3 $GPU3_UUID already has compute apps"; exit 3; fi
echo "GPU3 $GPU3_UUID has no compute apps -- claiming it"
echo "other devices left alone: $(nvidia-smi --query-gpu=uuid --format=csv,noheader | grep -v $GPU3_UUID | tr '\n' ' ')"
echo "--- inherited cpuset (must be 120-123) ---"
grep -E "Cpus_allowed_list|Mems_allowed_list" /proc/self/status
lscpu -p=CPU,NODE,SOCKET,CORE | grep -v '^#' | awk -F, '$1>=120'
echo "Thread(s) per core: $(lscpu | awk -F: '/Thread\(s\) per core/{gsub(/ /,"",$2);print $2}')"
numactl --show 2>/dev/null | grep -E "policy|physcpubind|membind"
free -g | head -2; cat /proc/loadavg
echo "--- colleague / llama processes (recorded, untouched) ---"
pgrep -a llama | head -3 || echo "  (no llama)"
ps -eo user,pcpu,comm --sort=-pcpu | awk 'NR<=6'

echo; echo "################ SOURCE / INPUT ################"
sha256sum "$BUNDLE"
git clone -q --branch integrate/round96-correctness-foundation "$BUNDLE" "$R/cand"
git -C "$R/cand" worktree add -q --detach "$R/main" "$BASE"
CAND=$(git -C "$R/cand" rev-parse HEAD)
echo "candidate $CAND"; echo "main      $BASE"
echo "candidate dirty=$(git -C $R/cand status --porcelain|wc -l) main dirty=$(git -C $R/main status --porcelain|wc -l)"
sha256sum "$T/movies.star"
( cd "$T/Movies" && sha256sum *.tiff | sha256sum | sed 's/^/movie digest-of-digests: /' )
ls "$T/Movies"/*.tiff | wc -l | sed 's/^/movies: /'
ls -l "$T/Movies/gain.mrc" 2>/dev/null || echo "NOTE: no gain.mrc in this tutorial tree"

echo; echo "################ BUILDS (CUDA=ON sm80, -j4) ################"
for arm in main cand; do
  echo "[$arm]"
  $VENV/bin/cmake -S "$R/$arm" -B "$R/$arm/build" -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=OFF > "$LOG/$arm-cfg.log" 2>&1
  echo "  configure exit=$?"
  $VENV/bin/cmake --build "$R/$arm/build" -j4 > "$LOG/$arm-build.log" 2>&1
  echo "  build exit=$?  errors=$(grep -cE 'error:' $LOG/$arm-build.log)"
  sha256sum "$R/$arm/build/motioncorr"
  ldd "$R/$arm/build/motioncorr" | grep -iE "cudart|cufft" | sed 's/^/  /'
done

echo; echo "################ NATIVE CUDA ALL-24 ON GPU3 ################"
export CUDA_VISIBLE_DEVICES=$GPU3_UUID     # select by UUID, not ordinal
echo "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
GAIN=""; [ -f "$T/Movies/gain.mrc" ] && GAIN="--gainref Movies/gain.mrc"
( sleep 60; echo "--- compute-app witness DURING the run ---"; \
  nvidia-smi --query-compute-apps=pid,process_name,used_memory,gpu_uuid --format=csv; \
  nvidia-smi --query-gpu=uuid,utilization.gpu,memory.used --format=csv,noheader ) > "$LOG/witness.log" 2>&1 &
W=$!
for arm in main cand; do
  echo "--- $arm ---"
  ( cd "$T" && /usr/bin/time -v "$R/$arm/build/motioncorr" --i movies.star --o "$R/out_$arm" \
      --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
      --bfactor 150 $GAIN --gpu 0 --j 4 --seed 1 ) > "$LOG/$arm-run.log" 2> "$LOG/$arm-run.err"
  echo "  exit=$?  products=$(ls $R/out_$arm/Movies/*.mrc 2>/dev/null | wc -l)"
  grep -E "Maximum resident set size|Elapsed \(wall" "$LOG/$arm-run.err" | sed 's/^/  /'
done
wait $W 2>/dev/null
echo "--- device witness sampled while the run was on GPU3 ---"; cat "$LOG/witness.log"

echo; echo "################ COMPARISON (trusted comparator, correct invocation) ################"
$VENV/bin/python3 "$R/cand/docs/integration_round96/scripts/compare_native_products.py" \
    --ref "$R/out_main" --test "$R/out_cand" \
    --comparator "$R/cand/tools/compare_motioncorr.py" \
    --python "$VENV/bin/python3" --json "$R/compare.json"
echo "comparison exit=$?"

echo; echo "################ CLOSE-OUT ################"
nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader; echo "(empty = nothing left running)"
nvidia-smi --query-gpu=index,uuid,memory.used --format=csv,noheader
date -u +"UTC %Y-%m-%dT%H:%M:%SZ"; echo "DONE pr110 GPU3 native"
