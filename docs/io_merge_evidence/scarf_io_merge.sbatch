#!/bin/bash
#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 01:00:00
#SBATCH -J mc-io-merge
#SBATCH -o /scratch/scarf1415/mc-io-merge-evidence/slurm-%j.out
set -euo pipefail
D=/scratch/scarf1415/mc-io-merge-evidence
BASE=/scratch/scarf1415/mc-issue77-reviewed
MAIN="$BASE/src-main-3510495/build-cuda/motioncorr"
MAIN_SRC="$BASE/src-main-3510495"
MAIN_OUT="$BASE/final-head-3510657/ab/out_main_j8"
T=/home/vol05/scarf1415/i53-scarf/relion30_tutorial
E="$D/evidence-$SLURM_JOB_ID"
mkdir -p "$E"
exec > "$E/job.log" 2>&1
export CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=8 TMPDIR=/tmp OPENBLAS_NUM_THREADS=1
hostname;date -Is;uptime;grep Cpus_allowed_list /proc/self/status
scontrol show job "$SLURM_JOB_ID"
nvidia-smi
[ -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]
[ "$(git -C "$MAIN_SRC" rev-parse HEAD)" = 1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26 ]
[ "$(sha256sum "$MAIN" | cut -d' ' -f1)" = 5299ebd0aedce467ba0d0f605aaf2554fd940690656f7daaa694c40e5cbd0ab1 ]
git -C "$MAIN_SRC" status --porcelain --untracked-files=no > "$E/baseline-status.txt"
[ ! -s "$E/baseline-status.txt" ]
cp "$BASE/final-head-3510657/parity.json" "$E/reused-baseline-parity-provenance.json"
cp "$MAIN_SRC/build-cuda/CMakeCache.txt" "$E/baseline-CMakeCache.txt"
cp "$BASE/evidence-3510495/dataset-movie-sha256.txt" "$E/reused-input-content-hashes.txt"
sha256sum "$T/movies.star" "$T/Movies/gain.mrc" > "$E/input-hashes.txt"
for label in standalone combined;do
 if [ "$label" = standalone ];then sha=7a4f93f782a970fd146527beb5fd49e64695c1dc;else sha=e4f6769b0e1eb565fb1aed8de760efe1e6dc86f6;fi
 src="$D/src-$label-$SLURM_JOB_ID"
 git init --quiet "$src";git -C "$src" fetch --quiet "$D/$label.bundle" "$sha";git -C "$src" checkout --quiet --detach "$sha"
 [ "$(git -C "$src" rev-parse HEAD)" = "$sha" ]
 git -C "$src" show -s --format=fuller HEAD > "$E/source-$label.txt"
 cmake -S "$src" -B "$src/build-cuda" -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DTIMING=ON -DBUILD_TESTING=OFF -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME" > "$E/configure-$label.log" 2>&1
 cmake --build "$src/build-cuda" --parallel 8 > "$E/build-$label.log" 2>&1
 cp "$src/build-cuda/CMakeCache.txt" "$E/CMakeCache-$label.txt"
 sha256sum "$src/build-cuda/motioncorr" >> "$E/binaries.sha256"
 ldd "$src/build-cuda/motioncorr" > "$E/linkage-$label.txt"
 mkdir -p "$E/ab-$label"
 cp -al "$MAIN_OUT" "$E/ab-$label/out_main_j8"
 (while true;do date -Is;nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader;sleep 1;done) > "$E/gpu-witness-$label.log" 2>&1 &
 sampler=$!
 cd "$T"
 set +e
 "$src/build-cuda/motioncorr" --i movies.star --o "$E/ab-$label/out_${label}_j8" --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --gpu 0 > "$E/run-$label.stdout" 2> "$E/run-$label.stderr"
 rc=$?
 kill "$sampler" 2>/dev/null;wait "$sampler" 2>/dev/null
 set -e
 echo "$rc" > "$E/run-$label.rc";[ "$rc" = 0 ]
 grep -q 'Using CUDA acceleration on GPU device' "$E/run-$label.stdout"
 grep -q motioncorr "$E/gpu-witness-$label.log"
 python3 "$D/harness/residency_witness.py" "$E/ab-$label/out_${label}_j8" > "$E/residency-$label.json"
 set +e
 python3 "$D/harness/compare_outputs.py" --repo "$MAIN_SRC" --ref-binary "$MAIN" --test-binary "$src/build-cuda/motioncorr" --ref-label main --test-label "$label" --tutorial "$T" --threads 8 --skip-run --backend CUDA --work "$E/ab-$label" --ref-output-root "$MAIN_OUT" --json "$E/parity-$label.json" > "$E/parity-$label.log" 2>&1
 echo "$?" > "$E/parity-$label.rc"
 set -e
 python3 - "$E/parity-$label.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['overall_graded']=='PASS',r['summary']
PY
done
mkdir -p "$E/combined-vs-standalone"
cp -al "$E/ab-standalone/out_standalone_j8" "$E/combined-vs-standalone/out_main_j8"
cp -al "$E/ab-combined/out_combined_j8" "$E/combined-vs-standalone/out_combined_j8"
set +e
python3 "$D/harness/compare_outputs.py" --repo "$MAIN_SRC" --ref-binary "$D/src-standalone-$SLURM_JOB_ID/build-cuda/motioncorr" --test-binary "$D/src-combined-$SLURM_JOB_ID/build-cuda/motioncorr" --ref-label main --test-label combined --tutorial "$T" --threads 8 --skip-run --backend CUDA --work "$E/combined-vs-standalone" --ref-output-root "$E/ab-standalone/out_standalone_j8" --test-output-root "$E/ab-combined/out_combined_j8" --json "$E/combined-vs-standalone.json" > "$E/combined-vs-standalone.log" 2>&1
echo "$?" > "$E/combined-vs-standalone.rc"
set -e
python3 - "$E/combined-vs-standalone.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['overall_graded']=='PASS',r['summary']
PY
nvidia-smi;date -Is
printf 'COMPLETE\n' > "$E/COMPLETE"
