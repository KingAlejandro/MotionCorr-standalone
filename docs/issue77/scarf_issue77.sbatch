#!/bin/bash
#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 03:00:00
#SBATCH -J mc-issue77
#SBATCH -o /scratch/scarf1415/mc-issue77-reviewed/slurm-%j.out
set -euo pipefail
D=/scratch/scarf1415/mc-issue77-reviewed
T=/home/vol05/scarf1415/i53-scarf/relion30_tutorial
BASELINE_SHA=1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26
: "${CANDIDATE_SHA:?Root must supply reviewed commit}"
export CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=8 TMPDIR=/tmp
E="$D/evidence-$SLURM_JOB_ID"
mkdir -p "$E"
exec > "$E/job.log" 2>&1
trap 'echo "FAILED at line $LINENO"' ERR
python3 -c "import sys,numpy; print(sys.executable,sys.version,numpy.__version__)" > "$E/python-runtime.txt"
python3 -m pip freeze >> "$E/python-runtime.txt"
hostname; date -Is; uptime; grep Cpus_allowed_list /proc/self/status
scontrol show job "$SLURM_JOB_ID"
nvidia-smi --query-gpu=index,name,uuid,driver_version,memory.total --format=csv
APPS=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)
[ -z "$APPS" ] || { echo "Device already occupied: $APPS"; exit 1; }
sha256sum "$D/source.bundle" "$D"/harness/*.py > "$E/input-hashes.txt"
for label in main candidate; do
  if [ "$label" = main ]; then sha=$BASELINE_SHA; else sha=$CANDIDATE_SHA; fi
  src="$D/src-$label-$SLURM_JOB_ID"
  git init --quiet "$src"
  git -C "$src" fetch --quiet "$D/source.bundle" "$sha"
  git -C "$src" checkout --quiet --detach "$sha"
  [ "$(git -C "$src" rev-parse HEAD)" = "$sha" ]
  git -C "$src" status --porcelain > "$E/status-$label.txt"
  [ ! -s "$E/status-$label.txt" ]
  git -C "$src" show -s --format=fuller HEAD > "$E/source-$label.txt"
  git -C "$src" rev-parse 'HEAD^{tree}' >> "$E/source-$label.txt"
  cmake -S "$src" -B "$src/build-cuda" -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DTIMING=ON -DBUILD_TESTING=OFF -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME" > "$E/configure-$label.log" 2>&1
  cmake --build "$src/build-cuda" --parallel 8 > "$E/build-$label.log" 2>&1
  sha256sum "$src/build-cuda/motioncorr" >> "$E/binaries.sha256"
  ldd "$src/build-cuda/motioncorr" > "$E/linkage-$label.txt"
  cp "$src/build-cuda/CMakeCache.txt" "$E/CMakeCache-$label.txt"
done
MAIN="$D/src-main-$SLURM_JOB_ID/build-cuda/motioncorr"
CAND="$D/src-candidate-$SLURM_JOB_ID/build-cuda/motioncorr"
OPTIONS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --gpu 0)
mkdir -p "$E/ab"
cd "$T"
sha256sum movies.star Movies/gain.mrc > "$E/dataset-input-hashes.txt"
find Movies -maxdepth 1 -name "*_frameImage.tiff" -printf "%f %s\n" | sort > "$E/dataset-inventory.txt"
for label in main candidate; do
  if [ "$label" = main ]; then binary=$MAIN; else binary=$CAND; fi
  ( while true; do date -Is; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader; sleep 1; done ) > "$E/gpu-witness-$label.log" 2>&1 &
  sampler=$!
  set +e
  /usr/bin/time -v "$binary" --i movies.star --o "$E/ab/out_${label}_j8" "${OPTIONS[@]}" > "$E/run-$label.stdout" 2> "$E/run-$label.time"
  rc=$?
  kill "$sampler" 2>/dev/null; wait "$sampler" 2>/dev/null
  set -e
  echo "$rc" > "$E/run-$label.rc"
  [ "$rc" = 0 ] || exit 1
  [ "$(grep -c 'Using CUDA acceleration on GPU device' "$E/run-$label.stdout")" -ge 1 ]
  python3 "$D/harness/residency_witness.py" "$E/ab/out_${label}_j8" > "$E/residency-$label.json"
  grep -q motioncorr "$E/gpu-witness-$label.log"
done
set +e
"$CAND" --i movies.star --o "$E/invalid-device" "${OPTIONS[@]}" --gpu 99 > "$E/invalid-device.stdout" 2> "$E/invalid-device.stderr"
rc=$?
echo "$rc" > "$E/invalid-device.rc"
set -e
[ "$rc" != 0 ] || { echo 'Invalid device incorrectly accepted'; exit 1; }
set +e
python3 "$D/harness/compare_outputs.py" --repo "$D/src-main-$SLURM_JOB_ID" --ref-binary "$MAIN" --test-binary "$CAND" --ref-label main --test-label candidate --tutorial "$T" --threads 8 --skip-run --work "$E/ab" --json "$E/parity.json" > "$E/parity.log" 2>&1
compare_rc=$?
echo "$compare_rc" > "$E/parity.rc"
set -e
# Auxiliary PDF differences remain visible. Numerical/coverage/control failure stops timings.
python3 - "$E/parity.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); assert r['overall_graded']=='PASS', r['summary']
PY
python3 "$D/harness/timing_blocks.py" --ref-binary "$MAIN" --test-binary "$CAND" --ref-label main --test-label candidate --tutorial "$T" --threads 8 --blocks 3 --work "$E/timing" --json "$E/timing.json" > "$E/timing.log" 2>&1
# Compare each timed pair, not just counts. Retain all outputs.
for block in 1 2 3; do
  pair="$E/timing-pair-$block"; mkdir -p "$pair"
  cp -al "$E/timing/t_main_b$block" "$pair/out_main_j8"
  cp -al "$E/timing/t_candidate_b$block" "$pair/out_candidate_j8"
  set +e
  python3 "$D/harness/compare_outputs.py" --repo "$D/src-main-$SLURM_JOB_ID" --ref-binary "$MAIN" --test-binary "$CAND" --ref-label main --test-label candidate --tutorial "$T" --threads 8 --skip-run --work "$pair" --json "$E/timing-parity-$block.json" > "$E/timing-parity-$block.log" 2>&1
  echo "$?" > "$E/timing-parity-$block.rc"
  set -e
  python3 - "$E/timing-parity-$block.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); assert r['overall_graded']=='PASS', r['summary']
PY
done
nvidia-smi; date -Is
printf 'COMPLETE\n' > "$E/COMPLETE"
