#!/bin/bash
#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 03:00:00
#SBATCH -J mc-io-split
#SBATCH -o /scratch/scarf1415/mc-io-split-evidence/slurm-%j.out
#
# Native CUDA evidence for PR #90 (issue #85) and PR #91 (issue #86).
#
# Builds happen inside the allocation, on an exclusive node, so nothing here
# runs on a login node or shares a GPU with another job. Both PR heads are
# compared against the same main build on the same backend in the same
# allocation. This is a same-backend regression comparison, not a claim about
# CPU/CUDA agreement or about RELION parity.
set -uo pipefail

# Slurm's -o file is the log. An earlier revision of this script routed stdout
# through `exec > >(tee ...)`; the tee died mid-job and the next write killed
# the script with SIGPIPE (job 3510351, FAILED 0:13, two minutes in, after the
# builds had already succeeded). Logging is now direct, and SIGPIPE is ignored.
trap '' PIPE

D=/scratch/scarf1415/mc-io-split-evidence
T=/home/vol05/scarf1415/i53-scarf/relion30_tutorial
MAIN_SHA=1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26
PR90_SHA=676f7632822b86bba25ead05a824084c2c0631d5
PR91_SHA=cb9c0a202d2fb12649560ff683c866a6679b13df

export CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=8
export TMPDIR=/tmp

mkdir -p "$D/evidence"
cd "$D"

echo "=== allocation and host ==="
date -Is; hostname
echo "SLURM_JOB_ID=$SLURM_JOB_ID SLURM_JOB_NODELIST=${SLURM_JOB_NODELIST:-} EXCLUSIVE=${SLURM_JOB_EXCLUSIVE:-unset}"
scontrol show job "$SLURM_JOB_ID" | grep -E "JobId|NumNodes|NumCPUs|TRES|Gres|Shared|OverSubscribe" || true
grep Cpus_allowed_list /proc/self/status; uptime; nproc
echo "=== device ==="
nvidia-smi
nvidia-smi --query-gpu=index,name,uuid,driver_version,memory.total --format=csv
echo "=== other compute apps on this device at job start (must be empty) ==="
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv

echo "=== bundles ==="
sha256sum "$HOME/mc-io-perf.bundle" "$HOME/mc-io-dmg.bundle"

stage () {  # name bundle sha
  local name=$1 bundle=$2 sha=$3
  echo "--- stage $name @ $sha ---"
  rm -rf "$D/src-$name"
  git init --quiet "$D/src-$name"
  git -C "$D/src-$name" fetch --quiet "$HOME/$bundle" \
      'refs/remotes/origin/*:refs/remotes/origin/*' || { echo "FETCH FAILED $name"; return 1; }
  git -C "$D/src-$name" checkout --quiet --detach "$sha" || { echo "CHECKOUT FAILED $name"; return 1; }
  local got; got=$(git -C "$D/src-$name" rev-parse HEAD)
  echo "HEAD=$got expected=$sha"
  [ "$got" = "$sha" ] || { echo "HEAD MISMATCH $name"; return 1; }
  echo "TREE=$(git -C "$D/src-$name" rev-parse 'HEAD^{tree}')"
  echo "STATUS: $(git -C "$D/src-$name" status --porcelain | wc -l) modified files (must be 0)"
}

stage main mc-io-perf.bundle "$MAIN_SHA" || exit 1
stage pr90 mc-io-perf.bundle "$PR90_SHA" || exit 1
stage pr91 mc-io-dmg.bundle  "$PR91_SHA" || exit 1

build () {
  local name=$1
  echo "=== build $name (CUDA=ON sm80, Release, TIMING=ON, 8 jobs, inside allocation) ==="
  cd "$D/src-$name"
  cmake -S . -B build-cuda -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=80 -DTIMING=ON -DBUILD_TESTING=ON \
      -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME" \
      > "$D/evidence/configure-cuda-$name.log" 2>&1 \
    || { echo "CONFIGURE FAILED $name"; tail -30 "$D/evidence/configure-cuda-$name.log"; return 1; }
  cmake --build build-cuda --parallel 8 > "$D/evidence/build-cuda-$name.log" 2>&1 \
    || { echo "BUILD FAILED $name"; tail -50 "$D/evidence/build-cuda-$name.log"; return 1; }
  echo "build $name OK"
  cd "$D"
}

for n in main pr90 pr91; do build "$n" || exit 1; done

echo "=== binaries ==="
sha256sum "$D"/src-*/build-cuda/motioncorr | tee "$D/evidence/binaries-cuda.sha256"
echo "=== CUDA linkage witness (compile-only CI cannot produce this) ==="
for n in main pr90 pr91; do
  echo "--- $n ---"
  ldd "$D/src-$n/build-cuda/motioncorr" | grep -E "cudart|cufft|libcuda" || echo "NO CUDA LIBS LINKED ($n)"
done | tee "$D/evidence/cuda-linkage.txt"

echo "=== CUDA hardware unit controls ==="
ctest --test-dir "$D/src-pr90/build-cuda" -R 'Cuda' --output-on-failure \
  > "$D/evidence/ctest-cuda-pr90.log" 2>&1
echo "ctest cuda pr90 exit=$?"; tail -20 "$D/evidence/ctest-cuda-pr90.log"

OPTIONS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
         --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8)

run_gpu () {  # label outdir
  local label=$1 outdir=$2
  echo "=== GPU run $label ==="
  rm -rf "$outdir"; mkdir -p "$outdir"
  # Sample the device while the run is in flight: a process resident on the GPU
  # with allocated memory is the execution witness the report relies on.
  ( while true; do
      echo "$(date -Is) $(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader)"
      sleep 2
    done ) > "$D/evidence/gpu-sample-$label.txt" 2>&1 &
  local sampler=$!
  cd "$T"
  /usr/bin/time -v "$D/src-$label/build-cuda/motioncorr" --i movies.star --o "$outdir" \
      "${OPTIONS[@]}" --gpu 0 > "$D/evidence/run-$label.stdout" 2> "$D/evidence/run-$label.time"
  local rc=$?
  kill "$sampler" 2>/dev/null; wait "$sampler" 2>/dev/null
  cd "$D"
  echo "$label exit=$rc"
  echo "--- runtime CUDA selection marker ---"
  grep -c "Using CUDA acceleration on GPU device" "$D/evidence/run-$label.stdout" \
    || echo "MARKER ABSENT ($label)"
  grep -m1 "Using CUDA acceleration on GPU device" "$D/evidence/run-$label.stdout" || true
  echo "--- device samples naming this run ---"
  grep -c motioncorr "$D/evidence/gpu-sample-$label.txt" || echo "NO DEVICE SAMPLE ($label)"
  return $rc
}

# A failed run is recorded and the job continues: a partial matrix with the
# failure visible is worth more than losing the remaining legs.
run_gpu main "$D/ab-pr90/out_main_j8"; echo "run_gpu main rc=$?"
run_gpu pr90 "$D/ab-pr90/out_pr90_j8"; echo "run_gpu pr90 rc=$?"
run_gpu pr91 "$D/ab-pr91/out_pr91_j8"; echo "run_gpu pr91 rc=$?"

echo "=== negative control: CUDA build asked for a device that does not exist ==="
cd "$T"
"$D/src-pr90/build-cuda/motioncorr" --i movies.star --o "$D/negctl" "${OPTIONS[@]}" \
    --gpu 99 > "$D/evidence/negctl-bad-device.log" 2>&1
echo "bad-device exit=$? (must be nonzero)"
tail -5 "$D/evidence/negctl-bad-device.log"
cd "$D"

# Same main tree for the PR91 comparison, hard-linked so rglob sees real files.
rm -rf "$D/ab-pr91/out_main_j8"
mkdir -p "$D/ab-pr91"
cp -al "$D/ab-pr90/out_main_j8" "$D/ab-pr91/out_main_j8"

echo "=== PR90 vs main, CUDA backend, 24 movies ==="
python3 "$D/harness/compare_outputs.py" --repo "$D/src-pr90" \
  --ref-binary "$D/src-main/build-cuda/motioncorr" --ref-label main \
  --test-binary "$D/src-pr90/build-cuda/motioncorr" --test-label pr90 \
  --tutorial "$T" --threads 8 --skip-run \
  --work "$D/ab-pr90" --json "$D/evidence/pr90_outputs_cuda_j8.json"
echo "pr90 cuda compare exit=$?"

echo "=== PR91 vs main, CUDA backend, 24 movies ==="
python3 "$D/harness/compare_outputs.py" --repo "$D/src-pr91" \
  --ref-binary "$D/src-main/build-cuda/motioncorr" --ref-label main \
  --test-binary "$D/src-pr91/build-cuda/motioncorr" --test-label pr91 \
  --tutorial "$T" --threads 8 --skip-run \
  --work "$D/ab-pr91" --json "$D/evidence/pr91_outputs_cuda_j8.json"
echo "pr91 cuda compare exit=$?"

echo "=== decoded buffer ordered-pixel identity, CUDA-enabled builds ==="
for n in main pr90; do
  bash "$D/harness/build_harness.sh" "$D/src-$n" "$D/src-$n/build-cuda" "$D/dump_decoded_$n" \
    > "$D/evidence/harness-build-$n.log" 2>&1 || echo "HARNESS BUILD FAILED $n"
done
if [ -x "$D/dump_decoded_main" ] && [ -x "$D/dump_decoded_pr90" ]; then
  python3 "$D/harness/compare_decoded.py" --repo "$D/src-pr90" \
    --ref-dumper "$D/dump_decoded_main" --test-dumper "$D/dump_decoded_pr90" \
    --work "$D/work" \
    --real-movie "$T/Movies/20170629_00021_frameImage.tiff" \
    --json "$D/evidence/decoded_pixel_identity_cuda.json"
  echo "decoded compare exit=$?"
fi

echo "=== device at job end ==="
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
date -Is
echo "=== SCARF GPU JOB DONE ==="
